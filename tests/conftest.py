"""Estado de processo do webhook (grupos já vistos) não pode vazar de um teste para o outro."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app import main


@pytest.fixture(autouse=True)
def _limpar_grupos_vistos() -> Iterator[None]:
    main._GRUPOS_JA_LOGADOS.clear()
    main._PENDENTES_JA_REGISTRADOS.clear()
    yield
    main._GRUPOS_JA_LOGADOS.clear()
    main._PENDENTES_JA_REGISTRADOS.clear()
