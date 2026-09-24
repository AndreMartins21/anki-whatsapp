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
from app.services.letras import LyricsProvider
from app.services.llm import Tutor

FUSO_PADRAO = ZoneInfo("America/Sao_Paulo")  # o mesmo padrão de `Settings.timezone`


@dataclass(frozen=True)
class Autor:
    """Quem escreveu a mensagem de um grupo (M16): o número (só dígitos), o nome que o WhatsApp
    informa (nunca o telefone) e os números mencionados na mensagem (para `!teacher`)."""

    numero: str
    nome: str | None = None
    mencionados: tuple[str, ...] = ()


@dataclass(frozen=True)
class Deps:
    repo: Repository
    tutor: Tutor
    conversa: Conversa
    agora: Callable[[], datetime]
    fuso: ZoneInfo = FUSO_PADRAO  # fuso do aluno, para mostrar horários de lembrete
    letras: LyricsProvider | None = None  # M13: fonte das letras do /song (None = indisponível)
    grupo_prefixo: str | None = None  # M16: o prefixo do grupo (`!`); `None` no privado
    autor: Autor | None = None  # M16: quem escreveu, em grupo

    @property
    def em_grupo(self) -> bool:
        return self.grupo_prefixo is not None

    @property
    def p(self) -> str:
        """O prefixo dos comandos que os textos citam: o do grupo, ou `/` no privado."""
        return self.grupo_prefixo or "/"

    @property
    def autor_id(self) -> str | None:
        return self.autor.numero if self.autor else None

    @property
    def cmd_lembretes(self) -> str:
        return f"{self.grupo_prefixo}reminder" if self.em_grupo else "/reminders"

    def sessao_vazia(self) -> Sessao:
        return Sessao(atualizado_em=self.agora())


async def bloq[**P, R](funcao: Callable[P, R], *args: P.args, **kwargs: P.kwargs) -> R:
    """Roda em thread código síncrono e bloqueante (Firestore, IA) sem travar o event loop."""
    return await asyncio.to_thread(funcao, *args, **kwargs)
