"""Testes de ponta a ponta do webhook `/waha/webhook` (seção 8.1), com payloads reais de
`tests/fixtures/`. Usa FakeChannel e um MemoryRepository — nunca toca a rede.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from app.channel.fake import FakeChannel
from app.config import Settings
from app.flows.conversa import Conversa
from app.flows.router import Router
from app.main import app, get_channel, get_repository, get_router, get_settings
from app.repo.memory import MemoryRepository
from app.services.fake_llm import FakeTutor
from tests.helpers import explicacao_stall

FIXTURES = Path(__file__).parent / "fixtures"
CHAT_ALLOWED = "5531999998888@c.us"


async def _sem_espera(_: float) -> None:
    return None


def _fixture(nome: str) -> dict[str, Any]:
    return cast(
        "dict[str, Any]", json.loads((FIXTURES / f"{nome}.json").read_text(encoding="utf-8"))
    )


@pytest.fixture
def fake_channel() -> FakeChannel:
    return FakeChannel()


@pytest.fixture
def cliente(fake_channel: FakeChannel) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None,
        ALLOWED_NUMBER="5531999998888",
        BOT_NUMBER="5531988887777",
        WAHA_API_KEY="fake-local-key",
        GCP_PROJECT_ID="meu-projeto-local",
        EXPORT_BUCKET="meu-projeto-vocabot-exports",
    )
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_channel] = lambda: fake_channel
    repo = MemoryRepository()
    router = Router(
        repo=repo,
        tutor=FakeTutor(explicacoes=[explicacao_stall(), explicacao_stall()]),
        conversa=Conversa(fake_channel, CHAT_ALLOWED, dormir=_sem_espera, atraso=lambda: 0.0),
        nivel_padrao="B1-B2",
        modo="guiado",
    )
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_router] = lambda: router
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_mensagem_de_texto_marca_como_lida_e_e_recebida(
    cliente: TestClient, fake_channel: FakeChannel
) -> None:
    resposta = cliente.post("/waha/webhook", json=_fixture("texto"))

    assert resposta.status_code == 200
    assert fake_channel.vistos == [CHAT_ALLOWED]
    assert len(fake_channel.textos_enviados) == 1
    chat_id, texto = fake_channel.textos_enviados[0]
    assert chat_id == CHAT_ALLOWED
    assert "STALL" in texto


def test_from_me_e_ignorada(cliente: TestClient, fake_channel: FakeChannel) -> None:
    resposta = cliente.post("/waha/webhook", json=_fixture("from_me"))

    assert resposta.status_code == 200
    assert fake_channel.vistos == []
    assert fake_channel.textos_enviados == []


def test_mensagem_de_grupo_e_ignorada(cliente: TestClient, fake_channel: FakeChannel) -> None:
    resposta = cliente.post("/waha/webhook", json=_fixture("grupo"))

    assert resposta.status_code == 200
    assert fake_channel.vistos == []


def test_midia_responde_que_so_entende_texto(
    cliente: TestClient, fake_channel: FakeChannel
) -> None:
    resposta = cliente.post("/waha/webhook", json=_fixture("midia"))

    assert resposta.status_code == 200
    assert fake_channel.vistos == [CHAT_ALLOWED]
    assert len(fake_channel.textos_enviados) == 1
    chat_id, texto = fake_channel.textos_enviados[0]
    assert chat_id == CHAT_ALLOWED
    assert "texto" in texto.lower()


def test_numero_nao_autorizado_e_ignorado(cliente: TestClient, fake_channel: FakeChannel) -> None:
    resposta = cliente.post("/waha/webhook", json=_fixture("numero_nao_autorizado"))

    assert resposta.status_code == 200
    assert fake_channel.vistos == []
    assert fake_channel.textos_enviados == []


def test_lid_resolvido_para_numero_permitido_e_processado(
    cliente: TestClient, fake_channel: FakeChannel
) -> None:
    fake_channel.lids_conhecidos["257161284317237@lid"] = "5531999998888"

    resposta = cliente.post("/waha/webhook", json=_fixture("lid"))

    assert resposta.status_code == 200
    assert fake_channel.vistos == [CHAT_ALLOWED]


def test_lid_resolvido_fica_em_cache_e_nao_consulta_o_waha_de_novo(
    cliente: TestClient, fake_channel: FakeChannel
) -> None:
    fake_channel.lids_conhecidos["257161284317237@lid"] = "5531999998888"
    cliente.post("/waha/webhook", json=_fixture("lid"))
    fake_channel.lids_conhecidos.clear()  # o WAHA "esqueceu" o mapeamento
    outra = _fixture("lid")
    outra["payload"]["id"] = "true_257161284317237@lid_LID00002"

    resposta = cliente.post("/waha/webhook", json=outra)

    assert resposta.status_code == 200
    assert fake_channel.vistos == [CHAT_ALLOWED, CHAT_ALLOWED]


def test_lid_resolvido_para_numero_nao_permitido_e_ignorado(
    cliente: TestClient, fake_channel: FakeChannel
) -> None:
    fake_channel.lids_conhecidos["257161284317237@lid"] = "5511888887777"

    resposta = cliente.post("/waha/webhook", json=_fixture("lid"))

    assert resposta.status_code == 200
    assert fake_channel.vistos == []


def test_lid_nao_encontrado_e_ignorado_com_um_log_que_diz_o_motivo(
    cliente: TestClient, fake_channel: FakeChannel, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        resposta = cliente.post("/waha/webhook", json=_fixture("lid"))

    assert resposta.status_code == 200
    assert fake_channel.vistos == []
    assert any("LID não resolvido" in registro.message for registro in caplog.records)


def test_mensagem_duplicada_e_processada_so_uma_vez(
    cliente: TestClient, fake_channel: FakeChannel
) -> None:
    primeira = cliente.post("/waha/webhook", json=_fixture("texto"))
    segunda = cliente.post("/waha/webhook", json=_fixture("duplicado"))

    assert primeira.status_code == 200
    assert segunda.status_code == 200
    assert fake_channel.vistos == [CHAT_ALLOWED]  # sendSeen só rodou na primeira vez


def test_session_status_working_e_so_logado(
    cliente: TestClient, fake_channel: FakeChannel, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        resposta = cliente.post("/waha/webhook", json=_fixture("session_status"))

    assert resposta.status_code == 200
    assert fake_channel.vistos == []
    assert any("WORKING" in registro.message for registro in caplog.records)


def test_session_status_fora_de_working_gera_warning(
    cliente: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    evento = _fixture("session_status")
    payload = evento["payload"]
    assert isinstance(payload, dict)
    payload["status"] = "FAILED"

    with caplog.at_level(logging.WARNING):
        resposta = cliente.post("/waha/webhook", json=evento)

    assert resposta.status_code == 200
    assert any(registro.levelno == logging.WARNING for registro in caplog.records)


def test_health_continua_respondendo_sem_dependencias(cliente: TestClient) -> None:
    resposta = cliente.get("/health")

    assert resposta.status_code == 200
    assert resposta.json() == {"ok": True}
