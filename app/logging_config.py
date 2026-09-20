"""Logs estruturados: uma linha JSON por evento, no stdout (o Docker/Cloud Logging coletam).

Sem segredo e sem número de telefone completo nos logs: use `mascarar_numero` e `id_curto`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
from datetime import UTC, datetime

_LOGGERS_DO_UVICORN = ("uvicorn", "uvicorn.error", "uvicorn.access")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        evento: dict[str, object] = {
            "severity": record.levelname,
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            evento["exception"] = self.formatException(record.exc_info)
        return json.dumps(evento, ensure_ascii=False)


def configurar_logs(nivel: str = "INFO") -> None:
    """Idempotente: troca os handlers do logger raiz e faz o uvicorn usar o mesmo formato."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    raiz = logging.getLogger()
    raiz.handlers[:] = [handler]
    raiz.setLevel(nivel.upper())
    for nome in _LOGGERS_DO_UVICORN:
        logger = logging.getLogger(nome)
        logger.handlers.clear()
        logger.propagate = True


def mascarar_numero(numero: str) -> str:
    """`5531999998888` -> `55*******8888`: dá para reconhecer sem expor o número."""
    if len(numero) <= 6:
        return "*" * len(numero)
    return f"{numero[:2]}{'*' * (len(numero) - 6)}{numero[-4:]}"


def id_curto(identificador: str) -> str:
    """O id de mensagem do WhatsApp contém o número; para log, só um resumo estável dele."""
    return hashlib.sha256(identificador.encode()).hexdigest()[:8]
