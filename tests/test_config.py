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


@pytest.mark.parametrize("campo", ["WAHA_HOOK_HMAC_KEY", "ANTHROPIC_API_KEY", "GEMINI_MODEL"])
def test_opcional_vazio_no_env_conta_como_nao_definido(
    monkeypatch: pytest.MonkeyPatch, campo: str
) -> None:
    _com_env(monkeypatch, **{campo: "  "})

    settings = Settings(_env_file=None)

    assert settings.waha_hook_hmac_key is None
    assert settings.anthropic_api_key is None
    assert settings.gemini_model is None


# --- M14: allowlist com vários alunos, grupos e dono (ADR-0017) --------------------------------


def _sem_numeros(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALLOWED_NUMBER", raising=False)
    monkeypatch.delenv("ALLOWED_NUMBERS", raising=False)


def test_allowed_number_antigo_continua_valendo_como_lista_de_um(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _com_env(monkeypatch)

    settings = Settings(_env_file=None)

    assert settings.numeros_permitidos == ["5531999998888"]


def test_allowed_numbers_e_lista_separada_por_virgula(monkeypatch: pytest.MonkeyPatch) -> None:
    _com_env(monkeypatch, ALLOWED_NUMBERS=" +55 31 99999-8888, 5511988887777 ,,")
    monkeypatch.delenv("ALLOWED_NUMBER")

    settings = Settings(_env_file=None)

    assert settings.numeros_permitidos == ["5531999998888", "5511988887777"]


def test_allowed_number_e_allowed_numbers_juntam_sem_repetir(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _com_env(monkeypatch, ALLOWED_NUMBERS="5511988887777,5531999998888")

    settings = Settings(_env_file=None)

    assert settings.numeros_permitidos == ["5531999998888", "5511988887777"]


def test_falha_sem_nenhum_numero_permitido(monkeypatch: pytest.MonkeyPatch) -> None:
    _com_env(monkeypatch)
    _sem_numeros(monkeypatch)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_dono_padrao_e_o_primeiro_numero_da_lista(monkeypatch: pytest.MonkeyPatch) -> None:
    _com_env(monkeypatch, ALLOWED_NUMBERS="5511988887777,5531999998888")
    monkeypatch.delenv("ALLOWED_NUMBER")

    assert Settings(_env_file=None).dono == "5511988887777"


def test_dono_padrao_e_o_allowed_number_antigo_mesmo_com_a_lista_nova(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """O número que já usava o bot é o dono; alunos novos em ALLOWED_NUMBERS não o substituem."""
    _com_env(monkeypatch, ALLOWED_NUMBERS="5511988887777")

    assert Settings(_env_file=None).dono == "5531999998888"


def test_owner_number_explicito_vence_o_padrao(monkeypatch: pytest.MonkeyPatch) -> None:
    _com_env(monkeypatch, OWNER_NUMBER="5531999998888", ALLOWED_NUMBERS="5511988887777")

    assert Settings(_env_file=None).dono == "5531999998888"


def test_grupos_permitidos_vazio_por_padrao_e_lista_quando_definido(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _com_env(monkeypatch)
    assert Settings(_env_file=None).grupos_permitidos == []

    monkeypatch.setenv("ALLOWED_GROUPS", "120363000000000001@g.us, 120363000000000002@g.us")

    assert Settings(_env_file=None).grupos_permitidos == [
        "120363000000000001@g.us",
        "120363000000000002@g.us",
    ]


# --- M15: limite de grupos e contato (ADR-0018) ------------------------------------------------


def test_max_groups_padrao_e_configuravel(monkeypatch: pytest.MonkeyPatch) -> None:
    _com_env(monkeypatch)
    assert Settings(_env_file=None).max_groups == 10

    monkeypatch.setenv("MAX_GROUPS", "3")

    assert Settings(_env_file=None).max_groups == 3


def test_max_groups_rejeita_valor_negativo(monkeypatch: pytest.MonkeyPatch) -> None:
    _com_env(monkeypatch, MAX_GROUPS="-1")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_contact_email_tem_padrao_e_vazio_volta_ao_padrao(monkeypatch: pytest.MonkeyPatch) -> None:
    _com_env(monkeypatch)
    padrao = Settings(_env_file=None).contact_email
    assert "@" in padrao

    monkeypatch.setenv("CONTACT_EMAIL", "ajuda@exemplo.com")
    assert Settings(_env_file=None).contact_email == "ajuda@exemplo.com"

    monkeypatch.setenv("CONTACT_EMAIL", "  ")
    assert Settings(_env_file=None).contact_email == padrao


def test_eh_dono_aceita_a_variacao_do_nono_digito(monkeypatch: pytest.MonkeyPatch) -> None:
    _com_env(monkeypatch, OWNER_NUMBER="5531999998888")
    settings = Settings(_env_file=None)

    assert settings.eh_dono("5531999998888")
    assert settings.eh_dono("553199998888")  # a conta registrada sem o 9
    assert not settings.eh_dono("5511988887777")


# --- M16: prefixo do grupo (ADR-0019) ----------------------------------------------------------


def test_group_prefix_padrao_e_exclamacao(monkeypatch: pytest.MonkeyPatch) -> None:
    _com_env(monkeypatch)

    assert Settings(_env_file=None).group_prefix == "!"


def test_group_prefix_configuravel_e_vazio_volta_ao_padrao(monkeypatch: pytest.MonkeyPatch) -> None:
    _com_env(monkeypatch, GROUP_PREFIX="#")
    assert Settings(_env_file=None).group_prefix == "#"

    monkeypatch.setenv("GROUP_PREFIX", "  ")
    assert Settings(_env_file=None).group_prefix == "!"


@pytest.mark.parametrize("invalido", ["/", "a", "1", "!!!!", "ab"])
def test_group_prefix_rejeita_barra_letra_numero_e_o_grande_demais(
    monkeypatch: pytest.MonkeyPatch, invalido: str
) -> None:
    """A barra é o prefixo do privado; letra ou número colidiria com o texto normal."""
    _com_env(monkeypatch, GROUP_PREFIX=invalido)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


# --- M17: revisão em grupo (ADR-0020) ----------------------------------------------------------


def test_revisao_em_grupo_tem_padroes_e_e_configuravel(monkeypatch: pytest.MonkeyPatch) -> None:
    _com_env(monkeypatch)
    padrao = Settings(_env_file=None)
    assert (padrao.limite_por_sessao_grupo, padrao.timeout_marcacao_horas) == (5, 3.0)

    monkeypatch.setenv("LIMITE_POR_SESSAO_GRUPO", "8")
    monkeypatch.setenv("TIMEOUT_MARCACAO_HORAS", "0.5")
    ajustado = Settings(_env_file=None)

    assert (ajustado.limite_por_sessao_grupo, ajustado.timeout_marcacao_horas) == (8, 0.5)


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("LIMITE_POR_SESSAO_GRUPO", "0"),
        ("TIMEOUT_MARCACAO_HORAS", "0"),
        ("TIMEOUT_MARCACAO_HORAS", "-1"),
    ],
)
def test_revisao_em_grupo_rejeita_valores_sem_sentido(
    monkeypatch: pytest.MonkeyPatch, campo: str, valor: str
) -> None:
    _com_env(monkeypatch, **{campo: valor})

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
