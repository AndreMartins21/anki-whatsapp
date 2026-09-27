"""Testes de app/domain/lembretes.py — horários e parser de `/lembretes` (M10)."""

from __future__ import annotations

from datetime import UTC, datetime, time

import pytest

from app.domain.lembretes import (
    horarios_do_dia,
    parse_lembretes,
    parse_tamanho_revisao,
    proximo_horario,
)


@pytest.mark.parametrize(
    ("quantidade", "inicio", "fim", "esperado"),
    [
        (1, 9, 21, [time(9, 0)]),
        (3, 9, 21, [time(9, 0), time(15, 0), time(21, 0)]),
        (2, 20, 23, [time(20, 0), time(23, 0)]),
        (5, 9, 21, [time(9, 0), time(12, 0), time(15, 0), time(18, 0), time(21, 0)]),
    ],
)
def test_horarios_do_dia(quantidade: int, inicio: int, fim: int, esperado: list[time]) -> None:
    assert horarios_do_dia(quantidade, inicio, fim) == esperado


def test_proximo_horario_no_mesmo_dia() -> None:
    agora = datetime(2026, 9, 22, 10, 0, tzinfo=UTC)

    assert proximo_horario(agora, 3, 9, 21) == datetime(2026, 9, 22, 15, 0, tzinfo=UTC)


def test_proximo_horario_vira_o_dia() -> None:
    agora = datetime(2026, 9, 22, 22, 0, tzinfo=UTC)

    assert proximo_horario(agora, 3, 9, 21) == datetime(2026, 9, 23, 9, 0, tzinfo=UTC)


def test_proximo_horario_exatamente_no_ultimo_horario_vira_o_dia() -> None:
    agora = datetime(2026, 9, 22, 21, 0, tzinfo=UTC)

    assert proximo_horario(agora, 3, 9, 21) == datetime(2026, 9, 23, 9, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("argumento", "esperado"),
    [
        ("3", (3, 9, 21, 7)),
        (" 3 ", (3, 9, 21, 7)),
        ("3 9h-22h", (3, 9, 22, 7)),
        ("1 20h-23h", (1, 20, 23, 7)),
        ("8", (8, 9, 21, 7)),
        ("3 10", (3, 9, 21, 10)),  # quantidade + tamanho da fila, sem mudar a janela
        ("3 9h-22h 10", (3, 9, 22, 10)),  # os três juntos (M24)
        ("3 9h-22h 1", (3, 9, 22, 1)),  # tamanho no mínimo
        ("3 9h-22h 20", (3, 9, 22, 20)),  # tamanho no máximo
    ],
)
def test_parse_lembretes_valido(argumento: str, esperado: tuple[int, int, int, int]) -> None:
    assert parse_lembretes(argumento) == esperado


@pytest.mark.parametrize(
    "argumento",
    [
        "0",  # abaixo do mínimo
        "9",  # acima do máximo
        "3 22h-9h",  # início depois do fim
        "3 9h-9h",  # janela vazia
        "off",
        "",
        "tres",
        "3 9-22",  # sem o "h"
        "3 9h-22h 0",  # tamanho da fila abaixo do mínimo
        "3 9h-22h 21",  # tamanho da fila acima do máximo
    ],
)
def test_parse_lembretes_invalido(argumento: str) -> None:
    assert parse_lembretes(argumento) is None


@pytest.mark.parametrize(
    ("argumento", "esperado"),
    [("7", 7), ("1", 1), ("20", 20)],
)
def test_parse_tamanho_revisao_valido(argumento: str, esperado: int) -> None:
    assert parse_tamanho_revisao(argumento) == esperado


@pytest.mark.parametrize("argumento", ["0", "21", "", "sete", "-1"])
def test_parse_tamanho_revisao_invalido(argumento: str) -> None:
    assert parse_tamanho_revisao(argumento) is None
