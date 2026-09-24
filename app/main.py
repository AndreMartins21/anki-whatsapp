"""Ponto de entrada FastAPI: `/health` e o webhook do WAHA (seção 8.1 da spec).

O webhook só filtra e responde 200 na hora; a conversa (IA, atrasos "humanos") roda em
segundo plano no `Router`, para o WAHA não esperar nem reenviar o evento.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac as hmac_lib
import json
import logging
import os
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from google.cloud import firestore
from pydantic import SecretStr, ValidationError
from starlette.concurrency import run_in_threadpool

from app import messages
from app.channel.base import ChannelComLid
from app.channel.parser import (
    GroupJoinEvent,
    MessageEvent,
    MessagePayload,
    SessionStatusEvent,
    deve_ignorar_chat,
    digitos_do_chat_id,
    eh_lid,
    numero_esta_na_lista,
    parse_evento,
)
from app.channel.waha import WahaChannel
from app.config import Settings
from app.domain.models import agora_utc
from app.flows import admin
from app.flows.conversa import Conversa
from app.flows.router import Router
from app.logging_config import configurar_logs, id_curto
from app.repo.base import Banco
from app.repo.firestore import FirestoreBanco
from app.repo.memory import MemoryBanco
from app.services.lembretes import Agendador
from app.services.letras import LrclibProvider
from app.services.llm import criar_tutor
from app.services.planilha import ExportadorExcel
from app.services.storage import Armazenamento, ArmazenamentoLocal, criar_armazenamento_gcs

logger = logging.getLogger(__name__)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # campos obrigatórios vêm do .env/ambiente em runtime


def _criar_banco(settings: Settings) -> Banco:
    """Firestore em produção (ou contra o emulador); em memória no desenvolvimento local,
    para nunca gravar por engano num Firestore real."""
    if settings.app_env == "prod" or os.environ.get("FIRESTORE_EMULATOR_HOST"):
        return FirestoreBanco(firestore.Client(project=settings.gcp_project_id))
    return MemoryBanco()


def _criar_armazenamento(settings: Settings) -> Armazenamento:
    """Cloud Storage em produção; em dev local, uma pasta `exports/` (que o git ignora)."""
    if settings.app_env == "prod":
        return criar_armazenamento_gcs(
            projeto=settings.gcp_project_id, bucket=settings.export_bucket
        )
    return ArmazenamentoLocal(Path("exports"))


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configurar_logs(settings.log_level)
    canal = WahaChannel(
        base_url=settings.waha_url,
        api_key=settings.waha_api_key,
        session=settings.waha_session,
    )
    letras = LrclibProvider(base_url=settings.lyrics_url)
    banco = _criar_banco(settings)
    app.state.channel = canal
    app.state.banco = banco
    router = Router(
        banco=banco,
        tutor=criar_tutor(settings),
        criar_conversa=lambda chat_id: Conversa(canal, chat_id),
        nivel_padrao=settings.user_level,
        status_da_sessao=canal.session_status,
        exportador=ExportadorExcel(_criar_armazenamento(settings)),
        fuso=ZoneInfo(settings.timezone),
        letras=letras,
    )
    app.state.router = router

    # M10: lembretes de revisão espaçada (seção 5.7, ADR-0012) — laço em segundo plano, um
    # minuto por vez; só dispara com um chat_id real já aprendido de uma mensagem recebida.
    agendador = Agendador(
        router=router,
        banco=banco,
        agora=agora_utc,
        fuso=ZoneInfo(settings.timezone),
        sair_do_grupo=canal.leave_group,
    )
    app.state.agendador = agendador
    tarefa_do_agendador = asyncio.create_task(agendador.rodar())
    try:
        yield
    finally:
        agendador.parar()
        tarefa_do_agendador.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await tarefa_do_agendador
        await canal.aclose()
        await letras.aclose()


app = FastAPI(title="vocabot", lifespan=_lifespan)


def get_channel(request: Request) -> ChannelComLid:
    channel: ChannelComLid = request.app.state.channel
    return channel


def get_banco(request: Request) -> Banco:
    banco: Banco = request.app.state.banco
    return banco


def get_router(request: Request) -> Router:
    router: Router = request.app.state.router
    return router


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/waha/webhook")
async def waha_webhook(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    channel: Annotated[ChannelComLid, Depends(get_channel)],
    banco: Annotated[Banco, Depends(get_banco)],
    router: Annotated[Router, Depends(get_router)],
    tarefas: BackgroundTasks,
) -> dict[str, bool]:
    corpo_bruto = await request.body()

    if settings.waha_hook_hmac_key is not None and not _hmac_valido(
        corpo_bruto, request.headers, settings.waha_hook_hmac_key
    ):
        logger.warning("webhook rejeitado: assinatura HMAC ausente ou inválida")
        raise HTTPException(status_code=401, detail="assinatura inválida")

    try:
        evento = parse_evento(json.loads(corpo_bruto))
    except ValueError as erro:
        # JSON inválido ou payload fora do formato esperado: nunca vira 500 (o WAHA reenviaria o
        # mesmo evento para sempre). Só os campos com problema vão ao log, nunca o conteúdo.
        campos = (
            sorted({".".join(map(str, e["loc"])) for e in erro.errors()})
            if isinstance(erro, ValidationError)
            else []
        )
        logger.warning("payload inválido no webhook (campos: %s)", campos or "json ilegível")
        return {"ok": True}

    if isinstance(evento, SessionStatusEvent):
        _tratar_status_sessao(evento)
        return {"ok": True}

    if isinstance(evento, GroupJoinEvent):
        try:
            await _tratar_entrada_em_grupo(evento, settings, channel, banco)
        except Exception:
            logger.exception("falha ao registrar a entrada em um grupo")
        return {"ok": True}

    if isinstance(evento, MessageEvent):
        try:
            await _tratar_mensagem(evento.payload, settings, channel, banco, router, tarefas)
        except Exception:
            # Antes de saber quem escreveu não há para quem avisar; depois, o aviso vai só ao
            # próprio chat (dentro de `_tratar_mensagem`), nunca a outro aluno.
            logger.exception("falha ao processar mensagem")
        return {"ok": True}

    logger.info("evento sem assinatura ignorado")
    return {"ok": True}


def _hmac_valido(corpo: bytes, cabecalhos: Mapping[str, str], chave: SecretStr) -> bool:
    assinatura_recebida = cabecalhos.get("X-Webhook-Hmac")
    algoritmo = cabecalhos.get("X-Webhook-Hmac-Algorithm", "").lower()
    if not assinatura_recebida or algoritmo != "sha512":
        return False
    esperado = hmac_lib.new(chave.get_secret_value().encode(), corpo, hashlib.sha512).hexdigest()
    return hmac_lib.compare_digest(esperado, assinatura_recebida)


async def _tratar_mensagem(
    payload: MessagePayload,
    settings: Settings,
    channel: ChannelComLid,
    banco: Banco,
    router: Router,
    tarefas: BackgroundTasks,
) -> None:
    if payload.from_me:
        logger.debug("mensagem própria ignorada: %s", id_curto(payload.id))
        return

    if payload.from_.endswith("@g.us"):
        await _tratar_mensagem_de_grupo(payload, settings, channel, banco)
        return

    if deve_ignorar_chat(payload.from_):
        logger.info("mensagem de status/canal ignorada")
        return

    numero_resolvido = await _numero_do_remetente(payload.from_, channel, banco)
    if numero_resolvido is None:
        logger.warning("LID não resolvido: o WAHA não achou o telefone do remetente; ignorada")
        return

    acesso = _acesso(settings, channel, banco)
    aluno = numero_esta_na_lista(numero_resolvido, settings.numeros_permitidos) or settings.eh_dono(
        numero_resolvido
    )
    e_admin = await run_in_threadpool(admin.eh_admin, acesso, numero_resolvido)

    # Responde ao número REAL do remetente (o que o WhatsApp informa). Ele passou pela allowlist,
    # mas pode diferir do número do .env no nono dígito: a conta pode estar registrada sem o 9, e
    # enviar para o número do .env dá "no LID found" no WAHA.
    chat_destino = f"{numero_resolvido}@c.us"

    if not aluno and not e_admin:
        # Sem plano: a IA nunca é chamada, nada é lido nem gravado, sem `sendSeen`. Só o aviso
        # (no máximo um por semana, ADR-0018) e depois silêncio.
        if payload.has_media or payload.body.strip():
            await _avisar_sem_plano(acesso, numero_resolvido, chat_destino)
        return

    try:
        await _despachar(
            payload, channel, banco, router, tarefas, chat_destino, acesso, numero_resolvido, aluno
        )
    except Exception:
        # Quem escreveu já está autorizado: o aviso vai só ao próprio chat, nunca a outro aluno.
        logger.exception("falha ao processar mensagem")
        with contextlib.suppress(Exception):
            await channel.send_text(chat_destino, messages.ERRO_INESPERADO)


async def _despachar(
    payload: MessagePayload,
    channel: ChannelComLid,
    banco: Banco,
    router: Router,
    tarefas: BackgroundTasks,
    chat_destino: str,
    acesso: admin.Acesso,
    numero: str,
    aluno: bool,
) -> None:
    if not payload.has_media and not payload.body.strip():
        # Sem texto nem mídia: o WAHA não conseguiu decifrar (ou é um tipo que não tratamos).
        logger.info("mensagem sem texto ignorada: %s", id_curto(payload.id))
        return

    if not await run_in_threadpool(banco.marcar_processada, payload.id, agora_utc()):
        logger.info("mensagem duplicada ignorada: %s", id_curto(payload.id))
        return

    await channel.send_seen(chat_destino)
    tarefas.add_task(_responder, router, payload, channel, chat_destino, acesso, numero, aluno)


async def _responder(
    router: Router,
    payload: MessagePayload,
    channel: ChannelComLid,
    chat_destino: str,
    acesso: admin.Acesso,
    numero: str,
    aluno: bool,
) -> None:
    """Roda depois do 200. É a fronteira do sistema: nada que aconteça aqui pode escapar."""
    try:
        if not payload.has_media and admin.eh_comando_de_admin(payload.body):
            resposta = await admin.comando_privado(acesso, payload.body, numero)
            if resposta is not None:
                await router.responder_avulso(chat_destino, resposta)
                return
        if not aluno:
            # Um admin que não é aluno só usa os comandos de admin: o resto é "sem plano".
            await _avisar_sem_plano(acesso, numero, chat_destino)
            return
        if payload.has_media:
            await router.midia_nao_suportada(chat_destino)
        else:
            await router.processar(payload.body, chat_destino)
    except Exception:
        logger.exception("falha ao processar mensagem")
        with contextlib.suppress(Exception):
            await channel.send_text(chat_destino, messages.ERRO_INESPERADO)


def _acesso(settings: Settings, channel: ChannelComLid, banco: Banco) -> admin.Acesso:
    return admin.Acesso(
        banco=banco,
        canal=channel,
        eh_dono=settings.eh_dono,
        grupos_fixos=settings.grupos_permitidos,
        max_grupos=settings.max_groups,
        agora=agora_utc,
        contato=settings.contact_email,
    )


async def _avisar_sem_plano(acesso: admin.Acesso, numero: str, chat_destino: str) -> None:
    """O aviso "você não tem um plano", no máximo uma vez por semana por número: a marca vive em
    `processed/`, então a TTL de 7 dias a expira sozinha."""
    if not await run_in_threadpool(
        acesso.banco.marcar_processada, _chave_do_aviso(numero), agora_utc()
    ):
        return
    logger.info("mensagem de número sem plano: aviso enviado")
    with contextlib.suppress(Exception):
        await acesso.canal.send_text(chat_destino, messages.sem_plano(acesso.contato))


def _chave_do_aviso(numero: str) -> str:
    """A marca do aviso vive em `processed/` (TTL de 7 dias) sem guardar o telefone em claro."""
    return "aviso_" + hashlib.sha256(numero.encode()).hexdigest()[:32]


_GRUPOS_JA_LOGADOS: set[str] = set()
_PENDENTES_JA_REGISTRADOS: set[str] = set()


def _logar_grupo_uma_vez(grupo_id: str) -> None:
    """Grupo que ainda ninguém ativou: o id vai ao log UMA vez por processo, para o dono
    reconhecê-lo. Nada mais sobre a mensagem é logado."""
    if grupo_id not in _GRUPOS_JA_LOGADOS:
        _GRUPOS_JA_LOGADOS.add(grupo_id)
        logger.info(
            "bot em grupo não ativado (grupo %s): ignorando tudo até um admin ativar", grupo_id
        )


async def _registrar_pendente(banco: Banco, grupo_id: str) -> None:
    """Guarda o grupo como pendente (o agendador sai dele depois de 24 h). Uma ida ao banco por
    grupo por processo: um grupo barulhento não gera uma escrita por mensagem."""
    if grupo_id in _PENDENTES_JA_REGISTRADOS:
        return
    await run_in_threadpool(banco.registrar_grupo_pendente, grupo_id, agora_utc())
    _PENDENTES_JA_REGISTRADOS.add(grupo_id)


async def _tratar_entrada_em_grupo(
    evento: GroupJoinEvent, settings: Settings, channel: ChannelComLid, banco: Banco
) -> None:
    grupo_id = evento.payload.group.id
    if await run_in_threadpool(admin.grupo_autorizado, _acesso(settings, channel, banco), grupo_id):
        return
    _logar_grupo_uma_vez(grupo_id)
    await _registrar_pendente(banco, grupo_id)


async def _tratar_mensagem_de_grupo(
    payload: MessagePayload, settings: Settings, channel: ChannelComLid, banco: Banco
) -> None:
    """M15: em grupo o bot só reage a `!activate`/`!deactivate` de um admin. O filtro vem antes de
    tudo (deduplicação, `sendSeen`): o resto é conversa entre pessoas, que o bot não lê nem grava."""
    grupo_id = payload.from_
    acesso = _acesso(settings, channel, banco)
    if not await run_in_threadpool(admin.grupo_autorizado, acesso, grupo_id):
        _logar_grupo_uma_vez(grupo_id)
        await _registrar_pendente(banco, grupo_id)

    comando = None if payload.has_media else admin.eh_comando_de_ativacao(payload.body)
    if comando is None:
        return  # o processamento dos comandos do grupo chega no M16
    if payload.participant is None:
        logger.info("comando de grupo sem participante: ignorado")
        return
    numero = await _numero_do_remetente(payload.participant, channel, banco)
    if numero is None or not await run_in_threadpool(admin.eh_admin, acesso, numero):
        return  # quem não é admin não recebe nada: o bot não revela que existe
    if not await run_in_threadpool(banco.marcar_processada, payload.id, agora_utc()):
        logger.info("mensagem duplicada ignorada: %s", id_curto(payload.id))
        return
    await channel.send_seen(grupo_id)
    await admin.tratar_ativacao_no_grupo(acesso, comando, grupo_id, numero)


async def _numero_do_remetente(chat_id: str, channel: ChannelComLid, banco: Banco) -> str | None:
    if not eh_lid(chat_id):
        return digitos_do_chat_id(chat_id)
    em_cache = await run_in_threadpool(banco.obter_numero_do_lid, chat_id)
    if em_cache is not None:
        return em_cache
    numero = await channel.resolve_lid(chat_id)
    if numero is not None:
        await run_in_threadpool(banco.salvar_numero_do_lid, chat_id, numero)
    return numero


def _tratar_status_sessao(evento: SessionStatusEvent) -> None:
    if evento.payload.status == "WORKING":
        logger.info("sessão do WAHA em WORKING")
    else:
        logger.warning("sessão do WAHA saiu de WORKING: %s", evento.payload.status)
