"""Testes de app/repo/dedup.py."""

from __future__ import annotations

from app.repo.dedup import DeduplicadorEmMemoria


def test_mensagem_nova_nao_esta_processada() -> None:
    dedup = DeduplicadorEmMemoria()

    assert dedup.ja_processada("msg-1") is False


def test_mensagem_marcada_fica_processada() -> None:
    dedup = DeduplicadorEmMemoria()

    dedup.marcar_processada("msg-1")

    assert dedup.ja_processada("msg-1") is True


def test_ids_diferentes_nao_se_confundem() -> None:
    dedup = DeduplicadorEmMemoria()

    dedup.marcar_processada("msg-1")

    assert dedup.ja_processada("msg-2") is False
