"""Testes de app/services/metricas_destino.py (M28, ADR-0029)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from app.services.metricas_destino import (
    DestinoEmMemoria,
    DestinoLocal,
    linhas_para_ndjson,
)

DIA = date(2026, 9, 28)


@dataclass(frozen=True)
class _LinhaDeTeste:
    dt: str
    n: int
    quando: datetime


def test_linhas_vazias_viram_bytes_vazios() -> None:
    assert linhas_para_ndjson([]) == b""


def test_uma_linha_por_objeto_separadas_por_quebra_de_linha() -> None:
    linhas = [
        _LinhaDeTeste(dt="2026-09-28", n=1, quando=datetime(2026, 9, 28, tzinfo=UTC)),
        _LinhaDeTeste(dt="2026-09-28", n=2, quando=datetime(2026, 9, 28, tzinfo=UTC)),
    ]

    saida = linhas_para_ndjson(linhas)

    linhas_json = saida.decode("utf-8").strip("\n").split("\n")
    assert len(linhas_json) == 2
    primeira = json.loads(linhas_json[0])
    assert primeira == {"dt": "2026-09-28", "n": 1, "quando": "2026-09-28T00:00:00+00:00"}


def test_destino_em_memoria_guarda_por_tabela_e_dia() -> None:
    destino = DestinoEmMemoria()
    linha = _LinhaDeTeste(dt="2026-09-28", n=1, quando=datetime(2026, 9, 28, tzinfo=UTC))

    destino.gravar("espacos", DIA, [linha])

    assert destino.gravados[("espacos", DIA)] == linhas_para_ndjson([linha])


def test_destino_local_grava_no_layout_hive(tmp_path: Path) -> None:
    destino = DestinoLocal(tmp_path)
    linha = _LinhaDeTeste(dt="2026-09-28", n=1, quando=datetime(2026, 9, 28, tzinfo=UTC))

    destino.gravar("espacos", DIA, [linha])

    arquivo = tmp_path / "espacos" / "dt=2026-09-28" / "parte-0.json"
    assert arquivo.is_file()
    assert json.loads(arquivo.read_text("utf-8").strip()) == {
        "dt": "2026-09-28",
        "n": 1,
        "quando": "2026-09-28T00:00:00+00:00",
    }


def test_destino_local_sobrescreve_com_lista_vazia(tmp_path: Path) -> None:
    destino = DestinoLocal(tmp_path)
    linha = _LinhaDeTeste(dt="2026-09-28", n=1, quando=datetime(2026, 9, 28, tzinfo=UTC))
    destino.gravar("espacos", DIA, [linha])

    destino.gravar("espacos", DIA, [])

    arquivo = tmp_path / "espacos" / "dt=2026-09-28" / "parte-0.json"
    assert arquivo.read_bytes() == b""
