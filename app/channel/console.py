"""ConsoleChannel (seção 8.4): o canal do simulador — a conversa aparece no terminal."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path


class ConsoleChannel:
    """Com `pasta`, os arquivos "enviados" são gravados lá (o simulador não tem WhatsApp)."""

    def __init__(self, saida: Callable[[str], None] = print, pasta: Path | None = None) -> None:
        self._saida = saida
        self._pasta = pasta

    async def send_file(
        self,
        chat_id: str,  # noqa: ARG002
        nome: str,
        conteudo: bytes,
        tipo: str,  # noqa: ARG002
        legenda: str = "",
    ) -> None:
        onde = ""
        if self._pasta is not None:
            self._pasta.mkdir(parents=True, exist_ok=True)
            destino = self._pasta / Path(nome).name
            destino.write_bytes(conteudo)
            onde = f"\n{destino.resolve()}"
        await self.send_text("", f"📎 {Path(nome).name} ({len(conteudo)} bytes)\n{legenda}{onde}")

    async def send_text(self, chat_id: str, text: str) -> None:  # noqa: ARG002
        corpo = "\n".join(f"│ {linha}" if linha else "│" for linha in text.splitlines())
        self._saida(f"┌─ 🤖 vocabot\n{corpo}\n└─")

    async def send_seen(self, chat_id: str) -> None:  # noqa: ARG002
        return None

    async def typing(self, chat_id: str, on: bool) -> None:  # noqa: ARG002
        if on:
            self._saida("  … digitando")
