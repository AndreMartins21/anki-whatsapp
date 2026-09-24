"""Testes de app/channel/parser.py: parsing dos eventos do WAHA e regras de allowlist."""

from __future__ import annotations

import pytest

from app.channel.parser import (
    GroupJoinEvent,
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


def test_mensagem_de_grupo_traz_o_participante_que_enviou() -> None:
    bruto = {
        "event": "message",
        "session": "default",
        "payload": {
            "id": "false_120363000000000000@g.us_ABC_5531999998888@c.us",
            "from": "120363000000000000@g.us",
            "fromMe": False,
            "participant": "5531999998888@c.us",
            "body": "!activate",
        },
    }

    evento = parse_evento(bruto)

    assert isinstance(evento, MessageEvent)
    assert evento.payload.participant == "5531999998888@c.us"


def test_mensagem_privada_nao_tem_participante() -> None:
    evento = parse_evento(
        {
            "event": "message",
            "session": "default",
            "payload": {"id": "x", "from": "5531999998888@c.us", "body": "oi"},
        }
    )

    assert isinstance(evento, MessageEvent)
    assert evento.payload.participant is None


def test_parseia_evento_de_entrada_em_grupo() -> None:
    bruto = {
        "event": "group.v2.join",
        "session": "default",
        "payload": {
            "group": {
                "id": "120363000000000000@g.us",
                "subject": "Turma A",
                "participants": [{"id": "5531999998888@c.us", "role": "admin"}],
            },
            "timestamp": 789456123,
            "_data": {},
        },
    }

    evento = parse_evento(bruto)

    assert isinstance(evento, GroupJoinEvent)
    assert evento.payload.group.id == "120363000000000000@g.us"
    assert evento.payload.group.subject == "Turma A"


def test_evento_de_entrada_em_grupo_sem_assunto_e_valido() -> None:
    evento = parse_evento(
        {
            "event": "group.v2.join",
            "session": "default",
            "payload": {"group": {"id": "120363000000000000@g.us"}},
        }
    )

    assert isinstance(evento, GroupJoinEvent)
    assert evento.payload.group.subject is None


def _mensagem(**extras: object) -> MessageEvent:
    evento = parse_evento(
        {
            "event": "message",
            "session": "default",
            "payload": {
                "id": "x",
                "from": "120363000000000000@g.us",
                "participant": "5531999998888@c.us",
                "body": "!add stall",
                **extras,
            },
        }
    )
    assert isinstance(evento, MessageEvent)
    return evento


@pytest.mark.parametrize(
    "extras",
    [
        {"_data": {"pushName": "Ana"}},
        {"_data": {"notifyName": "Ana"}},
        {"_data": {"Info": {"PushName": "Ana"}}},
        {"notifyName": "Ana"},
    ],
)
def test_nome_do_remetente_vem_do_payload_em_varios_formatos(extras: dict[str, object]) -> None:
    assert _mensagem(**extras).payload.nome_do_remetente() == "Ana"


def test_sem_nome_no_payload_o_nome_e_none_e_nunca_o_telefone() -> None:
    assert _mensagem(_data={}).payload.nome_do_remetente() is None
    assert _mensagem().payload.nome_do_remetente() is None


def test_ids_mencionados_sao_lidos_quando_o_payload_traz() -> None:
    evento = _mensagem(mentionedIds=["5511988887777@c.us", "999@lid"])

    assert evento.payload.mentioned_ids == ["5511988887777@c.us", "999@lid"]
    assert _mensagem().payload.mentioned_ids == []
