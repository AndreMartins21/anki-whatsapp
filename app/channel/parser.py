"""Parser dos eventos do webhook do WAHA (seção 8.1) e regras de allowlist (seção 8.2).

Fica isolado em `app/channel/` porque é específico do formato de payload do WAHA — a
lógica de negócio (fora de `channel/`) nunca deve depender destes tipos diretamente.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_SUFIXOS_IGNORADOS = ("@g.us", "@newsletter")
_CHAT_STATUS = "status@broadcast"


class MessagePayload(BaseModel):
    """Corpo de `payload` no evento `message` (confirmado na doc do WAHA)."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    timestamp: int = 0
    from_: str = Field(alias="from")
    from_me: bool = Field(default=False, alias="fromMe")
    # O GOWS manda `to` e `body` nulos quando não consegue decifrar a mensagem.
    to: str | None = None
    body: str = ""
    has_media: bool = Field(default=False, alias="hasMedia")

    @field_validator("body", mode="before")
    @classmethod
    def _sem_texto_e_string_vazia(cls, valor: object) -> object:
        return "" if valor is None else valor


class MessageEvent(BaseModel):
    event: Literal["message"]
    session: str
    payload: MessagePayload


class SessionStatusPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    status: str


class SessionStatusEvent(BaseModel):
    event: Literal["session.status"]
    session: str
    payload: SessionStatusPayload


def parse_evento(bruto: dict[str, Any]) -> MessageEvent | SessionStatusEvent | None:
    """Interpreta o corpo do webhook. `None` para eventos que não assinamos (seção 8.1)."""
    tipo = bruto.get("event")
    if tipo == "message":
        return MessageEvent.model_validate(bruto)
    if tipo == "session.status":
        return SessionStatusEvent.model_validate(bruto)
    return None


def deve_ignorar_chat(chat_id: str) -> bool:
    """Grupos, canais e status/broadcast (seção 8.1, passo 2) — nunca respondemos a eles."""
    return chat_id == _CHAT_STATUS or chat_id.endswith(_SUFIXOS_IGNORADOS)


def eh_lid(chat_id: str) -> bool:
    return chat_id.endswith("@lid")


def digitos_do_chat_id(chat_id: str) -> str:
    """Extrai só os dígitos de um chatId (`5531999998888@c.us` -> `5531999998888`)."""
    return re.sub(r"\D", "", chat_id.split("@", 1)[0])


def _variantes_com_e_sem_nono_digito(numero: str) -> set[str]:
    """Número de celular brasileiro: 55 + DDD (2) + [9] + linha (8). Aceita as duas formas."""
    digitos = re.sub(r"\D", "", numero)
    variantes = {digitos}
    if len(digitos) == 13 and digitos[4] == "9":
        variantes.add(digitos[:4] + digitos[5:])
    elif len(digitos) == 12:
        variantes.add(digitos[:4] + "9" + digitos[4:])
    return variantes


def numero_e_permitido(numero_resolvido: str, allowed_number: str) -> bool:
    """Compara aceitando a variação do nono dígito em ambos os lados (seção 8.2)."""
    return bool(
        _variantes_com_e_sem_nono_digito(numero_resolvido)
        & _variantes_com_e_sem_nono_digito(allowed_number)
    )
