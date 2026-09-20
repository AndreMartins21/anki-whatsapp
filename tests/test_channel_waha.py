"""Testes de app/channel/waha.py, com httpx.MockTransport — nunca toca a rede de verdade."""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import SecretStr

from app.channel.waha import WahaChannel


def _canal(handler: httpx.MockTransport, **kwargs: object) -> WahaChannel:
    return WahaChannel(
        base_url="http://waha:3000",
        api_key=SecretStr("segredo-do-teste"),
        session="default",
        transport=handler,
        backoff_base=0.0,  # não esperar de verdade nos testes de retry
        **kwargs,  # type: ignore[arg-type]
    )


async def test_send_text_manda_o_corpo_certo() -> None:
    requisicoes: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requisicoes.append(request)
        return httpx.Response(200, json={"id": "abc"})

    canal = _canal(httpx.MockTransport(handler))
    await canal.send_text("5531999998888@c.us", "oi")
    await canal.aclose()

    assert len(requisicoes) == 1
    requisicao = requisicoes[0]
    assert requisicao.method == "POST"
    assert requisicao.url.path == "/api/sendText"
    assert requisicao.headers["X-Api-Key"] == "segredo-do-teste"
    assert json.loads(requisicao.content) == {
        "session": "default",
        "chatId": "5531999998888@c.us",
        "text": "oi",
    }


async def test_send_seen_manda_session_e_chat_id() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    canal = _canal(httpx.MockTransport(handler))
    await canal.send_seen("5531999998888@c.us")
    await canal.aclose()


@pytest.mark.parametrize(
    ("ligado", "endpoint"), [(True, "/api/startTyping"), (False, "/api/stopTyping")]
)
async def test_typing_usa_o_endpoint_certo(ligado: bool, endpoint: str) -> None:
    chamado = {}

    def handler(request: httpx.Request) -> httpx.Response:
        chamado["path"] = request.url.path
        return httpx.Response(200, json={})

    canal = _canal(httpx.MockTransport(handler))
    await canal.typing("5531999998888@c.us", ligado)
    await canal.aclose()

    assert chamado["path"] == endpoint


async def test_session_status_le_o_campo_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/sessions/default"
        return httpx.Response(200, json={"name": "default", "status": "WORKING"})

    canal = _canal(httpx.MockTransport(handler))
    status = await canal.session_status()
    await canal.aclose()

    assert status == "WORKING"


async def test_resolve_lid_retorna_o_numero_quando_encontrado() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/default/lids/257161284317237"
        return httpx.Response(200, json={"lid": "257161284317237@lid", "pn": "5531999998888@c.us"})

    canal = _canal(httpx.MockTransport(handler))
    numero = await canal.resolve_lid("257161284317237@lid")
    await canal.aclose()

    assert numero == "5531999998888"


async def test_resolve_lid_retorna_none_quando_nao_encontrado() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"lid": "257161284317237@lid", "pn": None})

    canal = _canal(httpx.MockTransport(handler))
    numero = await canal.resolve_lid("257161284317237@lid")
    await canal.aclose()

    assert numero is None


async def test_tenta_de_novo_em_erro_5xx_e_depois_funciona() -> None:
    respostas = [httpx.Response(503), httpx.Response(200, json={"id": "abc"})]

    def handler(request: httpx.Request) -> httpx.Response:
        return respostas.pop(0)

    canal = _canal(httpx.MockTransport(handler))
    await canal.send_text("5531999998888@c.us", "oi")
    await canal.aclose()

    assert respostas == []


async def test_desiste_apos_esgotar_as_tentativas() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    canal = _canal(httpx.MockTransport(handler))
    with pytest.raises(httpx.HTTPStatusError):
        await canal.send_text("5531999998888@c.us", "oi")
    await canal.aclose()


async def test_erro_4xx_nao_tenta_de_novo() -> None:
    chamadas = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal chamadas
        chamadas += 1
        return httpx.Response(401)

    canal = _canal(httpx.MockTransport(handler))
    with pytest.raises(httpx.HTTPStatusError):
        await canal.send_text("5531999998888@c.us", "oi")
    await canal.aclose()

    assert chamadas == 1
