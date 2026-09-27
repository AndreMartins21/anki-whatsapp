"""Testes de app/logging_config.py."""

from __future__ import annotations

import json
import logging

import pytest

from app.logging_config import configurar_logs, id_curto, mascarar_numero, registrar_evento


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


def test_registrar_evento_inclui_os_campos_da_lista_branca(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configurar_logs("INFO")
    logger = logging.getLogger("teste")

    registrar_evento(logger, "lembrete_enviado", espaco="abcd1234", tipo_espaco="grupo", n=7)

    evento = json.loads(capsys.readouterr().out.strip())
    assert evento["evento"] == "lembrete_enviado"
    assert evento["message"] == "lembrete_enviado"
    assert evento["espaco"] == "abcd1234"
    assert evento["tipo_espaco"] == "grupo"
    assert evento["n"] == 7


def test_campo_fora_da_lista_branca_e_descartado(capsys: pytest.CaptureFixture[str]) -> None:
    configurar_logs("INFO")

    logging.getLogger("teste").info("evento comum", extra={"numero_do_aluno": "5531999998888"})

    evento = json.loads(capsys.readouterr().out.strip())
    assert "numero_do_aluno" not in evento


def test_ok_false_e_n_zero_aparecem_no_json(capsys: pytest.CaptureFixture[str]) -> None:
    """`getattr(record, campo, None)` não pode confundir `False`/`0` com "campo ausente"."""
    configurar_logs("INFO")
    logger = logging.getLogger("teste")

    registrar_evento(logger, "llm_chamada", metodo="explain", ok=False, n=0)

    evento = json.loads(capsys.readouterr().out.strip())
    assert evento["ok"] is False
    assert evento["n"] == 0


def test_configurar_logs_liga_o_handler_extra(capsys: pytest.CaptureFixture[str]) -> None:
    linhas_do_extra: list[str] = []

    class HandlerDeTeste(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            linhas_do_extra.append(record.getMessage())

    configurar_logs("INFO", handler_extra=HandlerDeTeste())
    logging.getLogger("teste").info("também vai para a nuvem")

    assert linhas_do_extra == ["também vai para a nuvem"]
    # o stdout continua funcionando normalmente (o handler extra não substitui o de sempre).
    assert json.loads(capsys.readouterr().out.strip())["message"] == "também vai para a nuvem"


def test_mascarar_numero() -> None:
    assert mascarar_numero("5531999998888") == "55*******8888"
    assert mascarar_numero("12345") == "*****"


def test_id_curto_nao_revela_o_numero_e_e_estavel() -> None:
    mensagem = "true_5531999998888@c.us_ABC"

    assert id_curto(mensagem) == id_curto(mensagem)
    assert "5531" not in id_curto(mensagem)
    assert len(id_curto(mensagem)) == 8
