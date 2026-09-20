"""Testes de app/services/storage.py — clientes do GCS substituídos por dublês, sem rede."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from app.services.storage import ArmazenamentoGcs, ArmazenamentoLocal


class _BlobFalso:
    def __init__(self, eventos: list[str]) -> None:
        self.eventos = eventos
        self.enviado: tuple[bytes, str] | None = None
        self.assinatura: dict[str, Any] = {}

    def upload_from_string(self, conteudo: bytes, content_type: str) -> None:
        self.eventos.append("upload")
        self.enviado = (conteudo, content_type)

    def generate_signed_url(self, **kwargs: Any) -> str:
        self.eventos.append("assinar")
        self.assinatura = kwargs
        return "https://storage.example/assinado"


def test_gcs_sobe_o_arquivo_e_assina_via_iam_com_validade_de_24h() -> None:
    eventos: list[str] = []
    blob = _BlobFalso(eventos)
    nomes: list[str] = []

    def blob_de(nome: str) -> _BlobFalso:
        nomes.append(nome)
        return blob

    credenciais = SimpleNamespace(service_account_email="vocabot-vm@proj.iam", token="token-falso")  # noqa: S106 — valor de teste
    armazenamento = ArmazenamentoGcs(
        bucket=SimpleNamespace(blob=blob_de),
        credenciais=credenciais,
        renovar=lambda _: eventos.append("renovar"),
    )

    link = armazenamento.enviar("exports/anki_2026-09-20_1200.txt", "olá".encode())

    assert link == "https://storage.example/assinado"
    assert nomes == ["exports/anki_2026-09-20_1200.txt"]
    assert blob.enviado == ("olá".encode(), "text/plain; charset=utf-8")
    assert eventos == ["upload", "renovar", "assinar"]  # o token é renovado antes de assinar
    assert blob.assinatura == {
        "version": "v4",
        "expiration": timedelta(hours=24),
        "method": "GET",
        "service_account_email": "vocabot-vm@proj.iam",
        "access_token": "token-falso",
        "response_disposition": 'attachment; filename="anki_2026-09-20_1200.txt"',
    }


def test_armazenamento_local_grava_o_arquivo_e_devolve_um_link_de_arquivo(tmp_path: Path) -> None:
    armazenamento = ArmazenamentoLocal(tmp_path / "exports")

    link = armazenamento.enviar("exports/anki_x.txt", b"conteudo")

    assert (tmp_path / "exports" / "anki_x.txt").read_bytes() == b"conteudo"
    assert link == (tmp_path / "exports" / "anki_x.txt").resolve().as_uri()
