"""Interface de canal (seção 8.4 da spec) — a lógica de negócio nunca importa o WAHA direto."""

from __future__ import annotations

from typing import Protocol


class Channel(Protocol):
    """Enviar texto e arquivo, marcar como lido, digitando. Implementações: WahaChannel, ConsoleChannel,
    FakeChannel — trocável no futuro por Cloud API ou Telegram sem tocar na lógica de negócio."""

    async def send_text(self, chat_id: str, text: str) -> None: ...

    async def send_file(
        self, chat_id: str, nome: str, conteudo: bytes, tipo: str, legenda: str = ""
    ) -> None:
        """Envia um arquivo (documento) para o chat, com legenda opcional."""
        ...

    async def send_seen(self, chat_id: str) -> None: ...

    async def typing(self, chat_id: str, on: bool) -> None: ...

    async def leave_group(self, chat_id: str) -> None:
        """Sai de um grupo (M15: o bot não fica em grupo que nenhum admin ativou)."""
        ...

    async def group_name(self, chat_id: str) -> str | None:
        """O assunto do grupo, só para o dono reconhecê-lo em `/groups`. Nunca levanta: sem nome,
        `None`."""
        ...


class ChannelComLid(Channel, Protocol):
    """Extensão específica do WAHA: resolver @lid para número de telefone (seção 8.2).

    Não faz parte do `Channel` genérico porque é um detalhe do WhatsApp/WAHA — só o
    webhook (app/main.py), que já é a fronteira com o WAHA, depende disto.
    """

    async def resolve_lid(self, lid: str) -> str | None: ...
