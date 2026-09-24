"""Testes de app/services/letras.py com httpx.MockTransport — nunca toca a rede de verdade. As
letras são inventadas (ADR-0016)."""

from __future__ import annotations

import httpx
import pytest

from app.domain.musica import Musica
from app.services.letras import USER_AGENT, LetrasIndisponiveis, LrclibProvider


def _registro(id_: int, **extra: object) -> dict[str, object]:
    return {
        "id": id_,
        "name": "Paper Plane",
        "trackName": "Paper Plane",
        "artistName": "The Inventors",
        "albumName": "Made Up",
        "duration": 180,
        "instrumental": False,
        "plainLyrics": "I wrote your name on a paper plane",
        "syncedLyrics": None,
        **extra,
    }


def _provider(handler: httpx.MockTransport) -> LrclibProvider:
    return LrclibProvider(base_url="https://lrclib.test", transport=handler, backoff_base=0.0)


async def test_busca_so_pelo_titulo_usa_track_name_e_manda_user_agent() -> None:
    requisicoes: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requisicoes.append(request)
        return httpx.Response(200, json=[_registro(1), _registro(2, instrumental=True)])

    provider = _provider(httpx.MockTransport(handler))
    musicas = await provider.buscar("paper plane")
    await provider.aclose()

    assert musicas == [
        Musica(1, "Paper Plane", "The Inventors", "I wrote your name on a paper plane"),
        Musica(2, "Paper Plane", "The Inventors", None),  # instrumental: sem letra
    ]
    (requisicao,) = requisicoes
    assert requisicao.url.path == "/api/search"
    assert dict(requisicao.url.params) == {"track_name": "paper plane"}
    assert requisicao.headers["User-Agent"] == USER_AGENT


async def test_sem_resultado_pelo_titulo_tenta_a_busca_livre() -> None:
    requisicoes: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requisicoes.append(request)
        vazio = "track_name" in request.url.params
        return httpx.Response(200, json=[] if vazio else [_registro(1)])

    provider = _provider(httpx.MockTransport(handler))
    assert [m.id for m in await provider.buscar("paper plane")] == [1]
    assert [dict(r.url.params) for r in requisicoes] == [
        {"track_name": "paper plane"},
        {"q": "paper plane"},
    ]


async def test_busca_com_artista_usa_os_campos_separados() -> None:
    requisicoes: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requisicoes.append(request)
        return httpx.Response(200, json=[])

    provider = _provider(httpx.MockTransport(handler))
    assert await provider.buscar("paper plane", "the inventors") == []
    assert dict(requisicoes[0].url.params) == {
        "track_name": "paper plane",
        "artist_name": "the inventors",
    }


async def test_obter_por_id_e_404_vira_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/get/7":
            return httpx.Response(200, json=_registro(7))
        return httpx.Response(404, json={"message": "not found"})

    provider = _provider(httpx.MockTransport(handler))
    musica = await provider.obter(7)
    assert musica is not None and musica.id == 7
    assert await provider.obter(8) is None


async def test_tenta_de_novo_em_5xx() -> None:
    respostas = [httpx.Response(503), httpx.Response(200, json=[_registro(1)])]

    def handler(request: httpx.Request) -> httpx.Response:
        return respostas.pop(0)

    provider = _provider(httpx.MockTransport(handler))
    assert [m.id for m in await provider.buscar("paper plane")] == [1]


async def test_falha_persistente_vira_letras_indisponiveis() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sem rede")

    provider = _provider(httpx.MockTransport(handler))
    with pytest.raises(LetrasIndisponiveis):
        await provider.buscar("paper plane")


async def test_4xx_nao_tenta_de_novo() -> None:
    chamadas = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal chamadas
        chamadas += 1
        return httpx.Response(429)

    provider = _provider(httpx.MockTransport(handler))
    with pytest.raises(LetrasIndisponiveis):
        await provider.buscar("paper plane")
    assert chamadas == 1


async def test_resposta_em_formato_inesperado() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"not": "a list"})

    provider = _provider(httpx.MockTransport(handler))
    with pytest.raises(LetrasIndisponiveis):
        await provider.buscar("paper plane")
