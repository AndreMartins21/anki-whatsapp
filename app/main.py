"""Ponto de entrada FastAPI.

O webhook do WAHA (seção 8.1 da spec) chega no M1. Por enquanto só o `/health`, usado
pelo healthcheck do `docker compose` (seção 10.7).
"""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="vocabot")


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}
