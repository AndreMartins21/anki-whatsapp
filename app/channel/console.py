"""ConsoleChannel (seção 8.4): o canal do simulador — a conversa aparece no terminal."""

from __future__ import annotations

from collections.abc import Callable


class ConsoleChannel:
    def __init__(self, saida: Callable[[str], None] = print) -> None:
        self._saida = saida

    async def send_text(self, chat_id: str, text: str) -> None:  # noqa: ARG002
        corpo = "\n".join(f"│ {linha}" if linha else "│" for linha in text.splitlines())
        self._saida(f"┌─ 🤖 vocabot\n{corpo}\n└─")

    async def send_seen(self, chat_id: str) -> None:  # noqa: ARG002
        return None

    async def typing(self, chat_id: str, on: bool) -> None:  # noqa: ARG002
        if on:
            self._saida("  … digitando")
