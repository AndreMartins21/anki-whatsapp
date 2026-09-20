"""Testes de app/config.py — Settings deve carregar a config da seção 4 da spec.

Nunca dependem de rede nem de segredo real: os valores usados aqui são todos falsos.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings


def _env_minimo() -> dict[str, str]:
    return {
        "ALLOWED_NUMBER": "5531999998888",
        "BOT_NUMBER": "5531988887777",
        "WAHA_API_KEY": "fake-local-key",
        "GCP_PROJECT_ID": "meu-projeto-local",
        "EXPORT_BUCKET": "meu-projeto-vocabot-exports",
    }


def _com_env(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> None:
    valores = {**_env_minimo(), **overrides}
    for chave, valor in valores.items():
        monkeypatch.setenv(chave, valor)


def test_carrega_com_os_campos_minimos_obrigatorios(monkeypatch: pytest.MonkeyPatch) -> None:
    _com_env(monkeypatch)

    settings = Settings(_env_file=None)

    assert settings.allowed_number == "5531999998888"
    assert settings.bot_number == "5531988887777"
    assert settings.gcp_project_id == "meu-projeto-local"
    assert settings.export_bucket == "meu-projeto-vocabot-exports"


def test_valores_padrao_seguem_a_secao_4_da_spec(monkeypatch: pytest.MonkeyPatch) -> None:
    _com_env(monkeypatch)

    settings = Settings(_env_file=None)

    assert settings.app_env == "local"
    assert settings.user_level == "B1-B2"
    assert settings.practice_mode == "guiado"
    assert settings.llm_provider == "vertex_gemini"
    assert settings.vertex_location == "global"
    assert settings.waha_url == "http://waha:3000"
    assert settings.waha_session == "default"
    assert settings.anthropic_model == "claude-haiku-4-5-20251001"
    assert settings.gemini_model is None
    assert settings.anthropic_api_key is None


@pytest.mark.parametrize("campo_ausente", ["ALLOWED_NUMBER", "GCP_PROJECT_ID", "WAHA_API_KEY"])
def test_falha_quando_falta_campo_obrigatorio(
    monkeypatch: pytest.MonkeyPatch, campo_ausente: str
) -> None:
    _com_env(monkeypatch)
    monkeypatch.delenv(campo_ausente, raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize("nivel", ["A2-B1", "B1-B2", "B2-C1"])
def test_aceita_todos_os_niveis_da_spec(monkeypatch: pytest.MonkeyPatch, nivel: str) -> None:
    _com_env(monkeypatch, USER_LEVEL=nivel)

    settings = Settings(_env_file=None)

    assert settings.user_level == nivel


def test_rejeita_nivel_fora_da_spec(monkeypatch: pytest.MonkeyPatch) -> None:
    _com_env(monkeypatch, USER_LEVEL="C2")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_rejeita_llm_provider_desconhecido(monkeypatch: pytest.MonkeyPatch) -> None:
    _com_env(monkeypatch, LLM_PROVIDER="openai")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_segredos_nao_aparecem_em_texto_puro_na_representacao(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _com_env(monkeypatch, ANTHROPIC_API_KEY="sk-ant-super-secreta")

    settings = Settings(_env_file=None)

    representacao = repr(settings)
    assert "fake-local-key" not in representacao
    assert "sk-ant-super-secreta" not in representacao
