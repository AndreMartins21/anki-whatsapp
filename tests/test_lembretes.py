"""Testes de app/domain/lembretes.py — horários e parser de `/lembretes` (M10)."""

from __future__ import annotations

from datetime import UTC, datetime, time

import pytest

from app.domain.lembretes import horarios_do_dia, parse_lembretes, proximo_horario


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
        ("3", (3, 9, 21)),
        (" 3 ", (3, 9, 21)),
        ("3 9h-22h", (3, 9, 22)),
        ("1 20h-23h", (1, 20, 23)),
        ("8", (8, 9, 21)),
    ],
)
def test_parse_lembretes_valido(argumento: str, esperado: tuple[int, int, int]) -> None:
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
    ],
)
def test_parse_lembretes_invalido(argumento: str) -> None:
    assert parse_lembretes(argumento) is None
