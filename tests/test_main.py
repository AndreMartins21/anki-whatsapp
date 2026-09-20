"""Testes de app/main.py — só o essencial do M0: o endpoint de health.

O webhook do WAHA (seção 8.1 da spec) chega no M1; aqui só garantimos que o app sobe e
responde ao healthcheck do compose.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

cliente = TestClient(app)


def test_health_responde_ok() -> None:
    resposta = cliente.get("/health")

    assert resposta.status_code == 200
    assert resposta.json() == {"ok": True}
