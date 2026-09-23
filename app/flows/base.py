"""O que os fluxos compartilham: dependências e a ponte para o código síncrono."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from app.domain.models import Sessao
from app.flows.conversa import Conversa
from app.repo.base import Repository
from app.services.llm import Tutor

FUSO_PADRAO = ZoneInfo("America/Sao_Paulo")  # o mesmo padrão de `Settings.timezone`


@dataclass(frozen=True)
class Deps:
    repo: Repository
    tutor: Tutor
    conversa: Conversa
    agora: Callable[[], datetime]
    fuso: ZoneInfo = FUSO_PADRAO  # fuso do aluno, para mostrar horários de lembrete

    def sessao_vazia(self) -> Sessao:
        return Sessao(atualizado_em=self.agora())


async def bloq[**P, R](funcao: Callable[P, R], *args: P.args, **kwargs: P.kwargs) -> R:
    """Roda em thread código síncrono e bloqueante (Firestore, IA) sem travar o event loop."""
    return await asyncio.to_thread(funcao, *args, **kwargs)
