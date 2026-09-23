"""Testes de app/domain/srs.py — SM-2 simplificado (M10, ADR-0011), função pura."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.models import Entry, SentidoSalvo
from app.domain.srs import FACILIDADE_MAXIMA, FACILIDADE_MINIMA, reagendar, vencida

AGORA = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)


def _entrada(**campos: object) -> Entry:
    base = {
        "slug": "stall",
        "palavra": "stall",
        "classe": "verb",
        "cefr_estimado": "B2",
        "sentido": SentidoSalvo(traducao="travar", definicao="to stop making progress"),
    }
    return Entry.model_validate(base | campos)


def test_sequencia_de_bom_cresce_1_3_e_depois_multiplica_pela_facilidade() -> None:
    e0 = _entrada()

    a1 = reagendar(e0, "bom", AGORA)
    assert a1.repeticoes == 1
    assert a1.intervalo_dias == pytest.approx(1.0)
    assert a1.proxima_revisao == AGORA + timedelta(days=1)

    e1 = _entrada(
        repeticoes=a1.repeticoes, intervalo_dias=a1.intervalo_dias, facilidade=a1.facilidade
    )
    a2 = reagendar(e1, "bom", AGORA)
    assert a2.repeticoes == 2
    assert a2.intervalo_dias == pytest.approx(3.0)

    e2 = _entrada(
        repeticoes=a2.repeticoes, intervalo_dias=a2.intervalo_dias, facilidade=a2.facilidade
    )
    a3 = reagendar(e2, "bom", AGORA)
    assert a3.repeticoes == 3
    assert a3.intervalo_dias == pytest.approx(3.0 * 2.5)  # facilidade parada em 2.5 com "bom"


def test_de_novo_zera_repeticoes_e_conta_lapso() -> None:
    entrada = _entrada(repeticoes=5, intervalo_dias=20.0, facilidade=2.3, lapsos=1)

    agendamento = reagendar(entrada, "de_novo", AGORA)

    assert agendamento.repeticoes == 0
    assert agendamento.intervalo_dias == 0.0
    assert agendamento.proxima_revisao == AGORA
    assert agendamento.lapsos == 2
    assert agendamento.facilidade == pytest.approx(2.1)


def test_dificil_cresce_mais_devagar_que_bom() -> None:
    entrada = _entrada(repeticoes=2, intervalo_dias=5.0, facilidade=2.5)

    dificil = reagendar(entrada, "dificil", AGORA)
    bom = reagendar(entrada, "bom", AGORA)

    assert dificil.intervalo_dias < bom.intervalo_dias


def test_facil_cresce_mais_rapido_que_bom() -> None:
    entrada = _entrada(repeticoes=2, intervalo_dias=5.0, facilidade=2.5)

    facil = reagendar(entrada, "facil", AGORA)
    bom = reagendar(entrada, "bom", AGORA)

    assert facil.intervalo_dias > bom.intervalo_dias


def test_facilidade_nunca_sai_do_intervalo() -> None:
    baixa = _entrada(facilidade=FACILIDADE_MINIMA)
    alta = _entrada(facilidade=FACILIDADE_MAXIMA)

    assert reagendar(baixa, "de_novo", AGORA).facilidade == FACILIDADE_MINIMA
    assert reagendar(baixa, "dificil", AGORA).facilidade == FACILIDADE_MINIMA
    assert reagendar(alta, "facil", AGORA).facilidade == FACILIDADE_MAXIMA


def test_vencida_cartao_novo_e_vencida() -> None:
    assert vencida(_entrada(proxima_revisao=None), AGORA) is True


def test_vencida_no_prazo_ou_vencido() -> None:
    futura = _entrada(proxima_revisao=AGORA + timedelta(days=1))
    passada = _entrada(proxima_revisao=AGORA - timedelta(days=1))
    agora_mesmo = _entrada(proxima_revisao=AGORA)

    assert vencida(futura, AGORA) is False
    assert vencida(passada, AGORA) is True
    assert vencida(agora_mesmo, AGORA) is True
