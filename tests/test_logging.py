"""Testes de app/logging_config.py."""

from __future__ import annotations

import json
import logging

import pytest

from app.logging_config import configurar_logs, id_curto, mascarar_numero


def test_log_sai_em_uma_linha_json_com_severity_e_message(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configurar_logs("INFO")

    logging.getLogger("teste").warning("algo %s", "aconteceu")

    linha = capsys.readouterr().out.strip()
    evento = json.loads(linha)
    assert evento["severity"] == "WARNING"
    assert evento["message"] == "algo aconteceu"
    assert evento["logger"] == "teste"
    assert "T" in evento["time"]


def test_excecao_vai_no_campo_exception(capsys: pytest.CaptureFixture[str]) -> None:
    configurar_logs("INFO")

    try:
        raise ValueError("falhou")
    except ValueError:
        logging.getLogger("teste").exception("deu ruim")

    evento = json.loads(capsys.readouterr().out.strip())
    assert "ValueError: falhou" in evento["exception"]


def test_nivel_filtra_e_configurar_duas_vezes_nao_duplica(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configurar_logs("WARNING")
    configurar_logs("WARNING")

    logging.getLogger("teste").info("não aparece")
    logging.getLogger("teste").error("aparece uma vez")

    linhas = capsys.readouterr().out.strip().splitlines()
    assert len(linhas) == 1


def test_mascarar_numero() -> None:
    assert mascarar_numero("5531999998888") == "55*******8888"
    assert mascarar_numero("12345") == "*****"


def test_id_curto_nao_revela_o_numero_e_e_estavel() -> None:
    mensagem = "true_5531999998888@c.us_ABC"

    assert id_curto(mensagem) == id_curto(mensagem)
    assert "5531" not in id_curto(mensagem)
    assert len(id_curto(mensagem)) == 8
