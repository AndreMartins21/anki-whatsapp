"""Testes de app/channel/parser.py: parsing dos eventos do WAHA e regras de allowlist."""

from __future__ import annotations

import pytest

from app.channel.parser import (
    MessageEvent,
    SessionStatusEvent,
    deve_ignorar_chat,
    digitos_do_chat_id,
    eh_lid,
    numero_e_permitido,
    parse_evento,
)


def test_parseia_evento_de_mensagem() -> None:
    bruto = {
        "event": "message",
        "session": "default",
        "payload": {
            "id": "true_5531999998888@c.us_ABC",
            "timestamp": 1758331200,
            "from": "5531999998888@c.us",
            "fromMe": False,
            "to": "5531988887777@c.us",
            "body": "stall",
            "hasMedia": False,
        },
    }

    evento = parse_evento(bruto)

    assert isinstance(evento, MessageEvent)
    assert evento.payload.from_ == "5531999998888@c.us"
    assert evento.payload.from_me is False
    assert evento.payload.body == "stall"


def test_parseia_evento_de_status_de_sessao() -> None:
    bruto = {
        "event": "session.status",
        "session": "default",
        "payload": {"name": "default", "status": "WORKING"},
    }

    evento = parse_evento(bruto)

    assert isinstance(evento, SessionStatusEvent)
    assert evento.payload.status == "WORKING"


def test_evento_desconhecido_vira_none() -> None:
    assert parse_evento({"event": "presence.update", "session": "default", "payload": {}}) is None


@pytest.mark.parametrize(
    ("chat_id", "esperado"),
    [
        ("120363000000000000@g.us", True),
        ("status@broadcast", True),
        ("551199990000@newsletter", True),
        ("5531999998888@c.us", False),
        ("257161284317237@lid", False),
    ],
)
def test_deve_ignorar_chat(chat_id: str, esperado: bool) -> None:
    assert deve_ignorar_chat(chat_id) is esperado


def test_eh_lid() -> None:
    assert eh_lid("257161284317237@lid") is True
    assert eh_lid("5531999998888@c.us") is False


def test_digitos_do_chat_id() -> None:
    assert digitos_do_chat_id("5531999998888@c.us") == "5531999998888"


@pytest.mark.parametrize(
    ("numero_resolvido", "allowed_number", "esperado"),
    [
        ("5531999998888", "5531999998888", True),
        ("553199998888", "5531999998888", True),  # resolvido sem o nono dígito
        ("5531999998888", "553199998888", True),  # allowed_number sem o nono dígito
        ("5511888887777", "5531999998888", False),  # número totalmente diferente
    ],
)
def test_numero_e_permitido(numero_resolvido: str, allowed_number: str, esperado: bool) -> None:
    assert numero_e_permitido(numero_resolvido, allowed_number) is esperado
