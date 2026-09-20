"""Testes do harness de evals (evals/run.py) — sem chamar API nenhuma."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.domain.models import Evaluation
from app.services.fake_llm import FakeLLMProvider
from app.services.llm import LLMTutor
from evals.run import (
    CAMINHO_PADRAO,
    Caso,
    ErroDeConfiguracao,
    avaliar,
    carregar_casos,
    main,
    montar_tutor,
)

VEREDITOS = {"correta", "correta_pouco_natural", "quase", "incorreta"}


def _avaliacao(veredito: str) -> Evaluation:
    return Evaluation(
        usa_palavra_alvo=True,
        sentido_correto=True,
        veredito=veredito,
        correcoes=[],
        versao_natural="A [[b]].",
        explicacao="ok",
    )


def _caso(id_: str, esperado: list[str]) -> Caso:
    return Caso.model_validate(
        {
            "id": id_,
            "palavra": "stall",
            "sentido": {"traducao": "travar", "definicao": "to stop making progress"},
            "frase": "The talks stalled.",
            "esperado": esperado,
        }
    )


def test_arquivo_de_casos_e_valido_e_cobre_todos_os_vereditos() -> None:
    casos = carregar_casos(CAMINHO_PADRAO)

    assert len(casos) >= 15
    assert len({c.id for c in casos}) == len(casos), "ids repetidos"
    cobertos = {v for c in casos for v in c.esperado}
    assert cobertos == VEREDITOS


def test_carregar_casos_rejeita_veredito_desconhecido(tmp_path: Path) -> None:
    arquivo = tmp_path / "casos.yaml"
    arquivo.write_text(
        "- id: x\n  palavra: a\n  sentido: {traducao: b, definicao: c}\n"
        "  frase: d\n  esperado: [otimo]\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="esperado"):
        carregar_casos(arquivo)


def test_avaliar_conta_acertos_e_aceita_mais_de_um_veredito() -> None:
    tutor = LLMTutor(
        FakeLLMProvider([_avaliacao("correta"), _avaliacao("quase"), _avaliacao("incorreta")]),
        modelo="m",
        modelo_avaliacao="m",
    )
    casos = [
        _caso("a", ["correta"]),
        _caso("b", ["correta_pouco_natural", "quase"]),
        _caso("c", ["quase"]),
    ]

    relatorio = avaliar(tutor, casos, "B1-B2")

    assert [r.acertou for r in relatorio.resultados] == [True, True, False]
    assert relatorio.acertos == 2
    assert relatorio.taxa == pytest.approx(2 / 3)


def test_avaliar_conta_falha_da_ia_como_erro_sem_derrubar_a_execucao() -> None:
    tutor = LLMTutor(
        FakeLLMProvider(["lixo", "lixo", _avaliacao("correta")]), modelo="m", modelo_avaliacao="m"
    )

    relatorio = avaliar(tutor, [_caso("a", ["correta"]), _caso("b", ["correta"])], "B1-B2")

    assert relatorio.resultados[0].erro is not None
    assert relatorio.resultados[0].acertou is False
    assert relatorio.resultados[1].acertou is True
    assert relatorio.erros == 1


def test_montar_tutor_vertex_exige_projeto_e_modelo() -> None:
    with pytest.raises(ErroDeConfiguracao, match="GCP_PROJECT_ID"):
        montar_tutor("vertex_gemini", None, {})
    with pytest.raises(ErroDeConfiguracao, match="modelo"):
        montar_tutor("vertex_gemini", None, {"GCP_PROJECT_ID": "p"})


def test_montar_tutor_anthropic_exige_a_chave() -> None:
    with pytest.raises(ErroDeConfiguracao, match="ANTHROPIC_API_KEY"):
        montar_tutor("anthropic", None, {})


def test_main_sem_configuracao_sai_com_erro_e_mensagem(
    capsys: pytest.CaptureFixture[str],
) -> None:
    codigo = main(["--provider", "vertex_gemini"], env={})

    assert codigo == 2
    assert "GCP_PROJECT_ID" in capsys.readouterr().err
