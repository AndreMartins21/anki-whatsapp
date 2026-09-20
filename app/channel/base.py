"""Interface de canal (seção 8.4 da spec) — a lógica de negócio nunca importa o WAHA direto."""

from __future__ import annotations

from typing import Protocol


class Channel(Protocol):
    """Enviar texto, marcar como lido, digitando. Implementações: WahaChannel, ConsoleChannel,
    FakeChannel — trocável no futuro por Cloud API ou Telegram sem tocar na lógica de negócio."""

    async def send_text(self, chat_id: str, text: str) -> None: ...

    async def send_seen(self, chat_id: str) -> None: ...

    async def typing(self, chat_id: str, on: bool) -> None: ...


class ChannelComLid(Channel, Protocol):
    """Extensão específica do WAHA: resolver @lid para número de telefone (seção 8.2).

    Não faz parte do `Channel` genérico porque é um detalhe do WhatsApp/WAHA — só o
    webhook (app/main.py), que já é a fronteira com o WAHA, depende disto.
    """

    async def resolve_lid(self, lid: str) -> str | None: ...
