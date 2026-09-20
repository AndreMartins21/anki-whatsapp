"""Deduplicação de mensagens pelo `id` (seção 8.1, passo 4; esquema em `processed/` na seção 7.1).

`DeduplicadorEmMemoria` é o que o M1 tem disponível — o Firestore ainda não existe (chega no
M2, junto com o `Repository`). A spec descreve a versão definitiva usando `create()`, que falha
se o ID já existe; quando o `Repository` for implementado, este protocolo deve ser substituído
por uma implementação sobre ele, e este módulo pode sumir.
"""

from __future__ import annotations

from typing import Protocol


class Deduplicator(Protocol):
    def ja_processada(self, message_id: str) -> bool: ...

    def marcar_processada(self, message_id: str) -> None: ...


class DeduplicadorEmMemoria:
    """Só vale para o processo atual — reinicia ao reiniciar o container."""

    def __init__(self) -> None:
        self._vistas: set[str] = set()

    def ja_processada(self, message_id: str) -> bool:
        return message_id in self._vistas

    def marcar_processada(self, message_id: str) -> None:
        self._vistas.add(message_id)
