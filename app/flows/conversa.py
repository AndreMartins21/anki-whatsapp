"""Comportamento "humano" ao responder (seção 5.6 da spec): mostra "digitando…" enquanto a IA
trabalha, espera de 1 a 2 s antes de cada envio e nunca manda mais de 3 mensagens seguidas
sem uma resposta do usuário. Também guarda o destino: sempre o chat do remetente autorizado.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from app.channel.base import Channel

logger = logging.getLogger(__name__)

MAX_MENSAGENS_SEGUIDAS = 3


def _atraso_humano() -> float:
    return random.uniform(1.0, 2.0)  # noqa: S311 — só um atraso de aparência, sem fim criptográfico


class Conversa:
    def __init__(
        self,
        channel: Channel,
        chat_id: str,
        *,
        dormir: Callable[[float], Awaitable[None]] = asyncio.sleep,
        atraso: Callable[[], float] = _atraso_humano,
        max_seguidas: int = MAX_MENSAGENS_SEGUIDAS,
    ) -> None:
        self._channel = channel
        self._chat_id = chat_id
        self._dormir = dormir
        self._atraso = atraso
        self._max_seguidas = max_seguidas
        self._seguidas = 0

    def definir_destino(self, chat_id: str) -> None:
        """O chat para onde as respostas vão. É o número REAL do remetente já autorizado (o que o
        WhatsApp informa), que pode diferir do ALLOWED_NUMBER no nono dígito brasileiro."""
        self._chat_id = chat_id

    def usuario_falou(self) -> None:
        self._seguidas = 0

    def nova_iniciativa(self) -> None:
        """O bot está iniciando a conversa (M10: revisão espaçada agendada), não respondendo a
        uma mensagem — também reseta o limite de mensagens seguidas (seção 5.6)."""
        self._seguidas = 0

    async def enviar(self, texto: str) -> None:
        if self._seguidas >= self._max_seguidas:
            logger.warning(
                "limite de %d mensagens sem resposta: envio descartado", self._max_seguidas
            )
            return
        await self._dormir(self._atraso())
        await self._channel.send_text(self._chat_id, texto)
        self._seguidas += 1

    async def enviar_arquivo(
        self, nome: str, conteudo: bytes, tipo: str, legenda: str = ""
    ) -> None:
        """Como `enviar`, mas para um arquivo. Levanta a exceção do canal se o envio falhar
        (o chamador decide o plano B); só um envio bem-sucedido conta no limite."""
        if self._seguidas >= self._max_seguidas:
            logger.warning(
                "limite de %d mensagens sem resposta: envio descartado", self._max_seguidas
            )
            return
        await self._dormir(self._atraso())
        await self._channel.send_file(self._chat_id, nome, conteudo, tipo, legenda)
        self._seguidas += 1

    @asynccontextmanager
    async def digitando(self) -> AsyncIterator[None]:
        await self._sinalizar(True)
        try:
            yield
        finally:
            await self._sinalizar(False)

    async def _sinalizar(self, ligado: bool) -> None:
        try:
            await self._channel.typing(self._chat_id, ligado)
        except Exception:  # o "digitando…" é cosmético: nunca pode derrubar a resposta
            logger.warning("não consegui atualizar o 'digitando…'", exc_info=True)
