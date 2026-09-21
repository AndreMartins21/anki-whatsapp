"""Ponto de entrada FastAPI: `/health` e o webhook do WAHA (seção 8.1 da spec).

O webhook só filtra e responde 200 na hora; a conversa (IA, atrasos "humanos") roda em
segundo plano no `Router`, para o WAHA não esperar nem reenviar o evento.
"""

from __future__ import annotations

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

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from google.cloud import firestore
from pydantic import SecretStr, ValidationError
from starlette.concurrency import run_in_threadpool

from app import messages
from app.channel.base import ChannelComLid
from app.channel.parser import (
    MessageEvent,
    MessagePayload,
    SessionStatusEvent,
    deve_ignorar_chat,
    digitos_do_chat_id,
    eh_lid,
    numero_e_permitido,
    parse_evento,
)
from app.channel.waha import WahaChannel
from app.config import Settings
from app.domain.models import agora_utc
from app.flows.conversa import Conversa
from app.flows.router import Router
from app.logging_config import configurar_logs, id_curto
from app.repo.base import Repository
from app.repo.firestore import FirestoreRepository
from app.repo.memory import MemoryRepository
from app.services.anki import ExportadorAnki
from app.services.llm import criar_tutor
from app.services.storage import Armazenamento, ArmazenamentoLocal, criar_armazenamento_gcs

logger = logging.getLogger(__name__)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # campos obrigatórios vêm do .env/ambiente em runtime


def _criar_repositorio(settings: Settings) -> Repository:
    """Firestore em produção (ou contra o emulador); em memória no desenvolvimento local,
    para nunca gravar por engano num Firestore real."""
    if settings.app_env == "prod" or os.environ.get("FIRESTORE_EMULATOR_HOST"):
        return FirestoreRepository(firestore.Client(project=settings.gcp_project_id))
    return MemoryRepository()


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
    repo = _criar_repositorio(settings)
    app.state.channel = canal
    app.state.repo = repo
    app.state.router = Router(
        repo=repo,
        tutor=criar_tutor(settings),
        conversa=Conversa(canal, f"{settings.allowed_number}@c.us"),
        nivel_padrao=settings.user_level,
        modo=settings.practice_mode,
        status_da_sessao=canal.session_status,
        exportador=ExportadorAnki(repo, _criar_armazenamento(settings)),
    )
    try:
        yield
    finally:
        await canal.aclose()


app = FastAPI(title="vocabot", lifespan=_lifespan)


def get_channel(request: Request) -> ChannelComLid:
    channel: ChannelComLid = request.app.state.channel
    return channel


def get_repository(request: Request) -> Repository:
    repo: Repository = request.app.state.repo
    return repo


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
    repo: Annotated[Repository, Depends(get_repository)],
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

    if isinstance(evento, MessageEvent):
        try:
            await _tratar_mensagem(evento.payload, settings, channel, repo, router, tarefas)
        except Exception:
            logger.exception("falha ao processar mensagem")
            chat_destino = f"{settings.allowed_number}@c.us"
            with contextlib.suppress(Exception):
                await channel.send_text(chat_destino, messages.ERRO_INESPERADO)
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
    repo: Repository,
    router: Router,
    tarefas: BackgroundTasks,
) -> None:
    if payload.from_me:
        logger.debug("mensagem própria ignorada: %s", id_curto(payload.id))
        return

    if deve_ignorar_chat(payload.from_):
        logger.info("mensagem de grupo/status/canal ignorada")
        return

    numero_resolvido = await _numero_do_remetente(payload.from_, channel, repo)
    if numero_resolvido is None:
        logger.warning("LID não resolvido: o WAHA não achou o telefone do remetente; ignorada")
        return
    if not numero_e_permitido(numero_resolvido, settings.allowed_number):
        logger.warning("mensagem de número não autorizado ignorada")
        return

    if not payload.has_media and not payload.body.strip():
        # Sem texto nem mídia: o WAHA não conseguiu decifrar (ou é um tipo que não tratamos).
        logger.info("mensagem sem texto ignorada: %s", id_curto(payload.id))
        return

    if not await run_in_threadpool(repo.marcar_processada, payload.id, agora_utc()):
        logger.info("mensagem duplicada ignorada: %s", id_curto(payload.id))
        return

    chat_destino = f"{settings.allowed_number}@c.us"
    await channel.send_seen(chat_destino)

    tarefas.add_task(_responder, router, payload, channel, chat_destino)


async def _responder(
    router: Router, payload: MessagePayload, channel: ChannelComLid, chat_destino: str
) -> None:
    """Roda depois do 200. É a fronteira do sistema: nada que aconteça aqui pode escapar."""
    try:
        if payload.has_media:
            await router.midia_nao_suportada()
        else:
            await router.processar(payload.body)
    except Exception:
        logger.exception("falha ao processar mensagem")
        with contextlib.suppress(Exception):
            await channel.send_text(chat_destino, messages.ERRO_INESPERADO)


async def _numero_do_remetente(
    chat_id: str, channel: ChannelComLid, repo: Repository
) -> str | None:
    if not eh_lid(chat_id):
        return digitos_do_chat_id(chat_id)
    em_cache = await run_in_threadpool(repo.obter_numero_do_lid, chat_id)
    if em_cache is not None:
        return em_cache
    numero = await channel.resolve_lid(chat_id)
    if numero is not None:
        await run_in_threadpool(repo.salvar_numero_do_lid, chat_id, numero)
    return numero


def _tratar_status_sessao(evento: SessionStatusEvent) -> None:
    if evento.payload.status == "WORKING":
        logger.info("sessão do WAHA em WORKING")
    else:
        logger.warning("sessão do WAHA saiu de WORKING: %s", evento.payload.status)
