"""Ponto de entrada FastAPI: `/health` e o webhook do WAHA (seção 8.1 da spec).

A máquina de estados (M2) e os fluxos completos (M4) ainda não existem — uma mensagem de
texto válida só é registrada em log por enquanto (`_despachar_ao_roteador`).
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
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from google.cloud import firestore
from pydantic import SecretStr
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
from app.repo.base import Repository
from app.repo.firestore import FirestoreRepository
from app.repo.memory import MemoryRepository

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


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    canal = WahaChannel(
        base_url=settings.waha_url,
        api_key=settings.waha_api_key,
        session=settings.waha_session,
    )
    app.state.channel = canal
    app.state.repo = _criar_repositorio(settings)
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


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/waha/webhook")
async def waha_webhook(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    channel: Annotated[ChannelComLid, Depends(get_channel)],
    repo: Annotated[Repository, Depends(get_repository)],
) -> dict[str, bool]:
    corpo_bruto = await request.body()

    if settings.waha_hook_hmac_key is not None and not _hmac_valido(
        corpo_bruto, request.headers, settings.waha_hook_hmac_key
    ):
        logger.warning("webhook rejeitado: assinatura HMAC ausente ou inválida")
        raise HTTPException(status_code=401, detail="assinatura inválida")

    evento = parse_evento(json.loads(corpo_bruto))

    if isinstance(evento, SessionStatusEvent):
        _tratar_status_sessao(evento)
        return {"ok": True}

    if isinstance(evento, MessageEvent):
        try:
            await _tratar_mensagem(evento.payload, settings, channel, repo)
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
) -> None:
    if payload.from_me:
        logger.debug("mensagem própria ignorada: %s", payload.id)
        return

    if deve_ignorar_chat(payload.from_):
        logger.info("mensagem de grupo/status/canal ignorada")
        return

    numero_resolvido = await _numero_do_remetente(payload.from_, channel, repo)
    if numero_resolvido is None or not numero_e_permitido(
        numero_resolvido, settings.allowed_number
    ):
        logger.warning("mensagem de número não autorizado ignorada")
        return

    if not await run_in_threadpool(repo.marcar_processada, payload.id, agora_utc()):
        logger.info("mensagem duplicada ignorada: %s", payload.id)
        return

    chat_destino = f"{settings.allowed_number}@c.us"
    await channel.send_seen(chat_destino)

    if payload.has_media:
        await channel.send_text(chat_destino, messages.MIDIA_NAO_SUPORTADA)
        return

    await run_in_threadpool(_despachar_ao_roteador, payload)


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


def _despachar_ao_roteador(payload: MessagePayload) -> None:
    """Placeholder síncrono: a máquina de estados (M2) e os fluxos (M4) plugam aqui."""
    logger.info("mensagem de texto recebida, aguardando roteador: %r", payload.body)


def _tratar_status_sessao(evento: SessionStatusEvent) -> None:
    if evento.payload.status == "WORKING":
        logger.info("sessão do WAHA em WORKING")
    else:
        logger.warning("sessão do WAHA saiu de WORKING: %s", evento.payload.status)
