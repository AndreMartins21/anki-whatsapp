"""Testes do simulador de terminal (M6): o ciclo completo, sem WhatsApp nem IA."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from sim.__main__ import main


def _executar(falas: list[str], tmp_path: Path, *argv: str) -> tuple[int, str]:
    fila: Iterator[str] = iter(falas)
    saida: list[str] = []
    codigo = main(list(argv), entrada=lambda _: next(fila), saida=saida.append, exports=tmp_path)
    return codigo, "\n".join(saida)


def test_ciclo_completo_no_terminal(tmp_path: Path) -> None:
    codigo, tela = _executar(
        [
            "stall",  # sem contexto e com dois sentidos: pergunta qual
            "1",
            "1",  # escrever uma frase
            "The negotiations stalled after the first meeting.",
            "3",  # concluir -> oferece expansões
            "1,2",
            "2",  # praticar depois
            "/lista",
            "/exportar",
            "sair",
        ],
        tmp_path,
    )

    assert codigo == 0
    assert "Qual sentido de *stall*" in tela
    assert "*STALL* (verbo) · B2" in tela
    assert "Manda a sua frase com *stall*" in tela
    assert "✅ *Perfeita!*" in tela
    assert "💾 *stall* salvo!" in tela
    assert "Criei 2 entradas novas" in tela
    assert "✅ stall — travar, emperrar" in tela
    assert "1 cartão no arquivo do Anki" in tela
    assert "2 palavra(s) ficaram de fora" in tela  # as duas expansões ainda não têm frase
    (arquivo,) = list(tmp_path.glob("anki_*.txt"))
    assert "The negotiations <b>stalled</b> after the first meeting." in arquivo.read_text(
        encoding="utf-8"
    )


def test_palavra_com_frase_de_contexto_pula_a_pergunta_de_sentido(tmp_path: Path) -> None:
    _, tela = _executar(["stall | the talks stalled", "sair"], tmp_path)

    assert "Qual sentido" not in tela
    assert "O que você quer fazer?" in tela


def test_modo_producao_primeiro(tmp_path: Path) -> None:
    _, tela = _executar(
        ["stall | the talks stalled", "sair"], tmp_path, "--modo", "producao_primeiro"
    )

    assert "Escreve uma frase com *stall*" in tela
    assert "Me dá um exemplo" in tela


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
