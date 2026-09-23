"""Testes do simulador de terminal (M6/M9): o ciclo completo, sem WhatsApp nem IA de verdade."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from openpyxl import load_workbook

from sim.__main__ import main


def _executar(falas: list[str], tmp_path: Path, *argv: str) -> tuple[int, str]:
    fila: Iterator[str] = iter(falas)
    saida: list[str] = []
    codigo = main(list(argv), entrada=lambda _: next(fila), saida=saida.append, exports=tmp_path)
    return codigo, "\n".join(saida)


def test_ciclo_completo_no_terminal(tmp_path: Path) -> None:
    codigo, tela = _executar(
        [
            "stall | the talks stalled",
            "1",  # see more examples
            "The negotiations stalled after the first meeting.",
            "3",  # just save
            "/list",
            "/info 1",
            "/export",
            "sair",
        ],
        tmp_path,
    )

    assert codigo == 0
    assert "*stall* (verb) — B2" in tela
    assert "📝 *Examples with stall*" in tela
    assert "✅ *Perfect!*" in tela
    assert "✅ Saved: *stall*." in tela
    assert "1. ✅ stall — travar, emperrar" in tela
    assert "✍️ *Your sentences*" in tela
    assert "1 word in the spreadsheet" in tela
    (arquivo,) = list(tmp_path.glob("vocabot_*.xlsx"))
    livro = load_workbook(arquivo)
    assert livro.sheetnames == ["Words", "Sentences", "Synonyms"]
    assert livro["Words"]["B2"].value == "stall"


def test_palavra_com_frase_de_contexto_mostra_o_card_direto(tmp_path: Path) -> None:
    _, tela = _executar(["stall | the talks stalled", "sair"], tmp_path)

    assert "*stall* (verb) — B2" in tela
    assert "Just save" in tela


def test_fim_da_entrada_encerra_sem_erro(tmp_path: Path) -> None:
    def acabou(_: str) -> str:
        raise EOFError

    codigo = main([], entrada=acabou, saida=lambda _: None, exports=tmp_path)

    assert codigo == 0


def test_real_llm_sem_configuracao_sai_com_erro(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    codigo = main(["--real-llm"], entrada=input, saida=lambda _: None, env={}, exports=tmp_path)

    assert codigo == 2
    assert "GCP_PROJECT_ID" in capsys.readouterr().err
