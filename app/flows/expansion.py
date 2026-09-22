"""Expansões (M9): depois de salvar (Case D), sugere até 3 expressões relacionadas como texto —
sem menu, sem criar entradas novas sozinho. Se o aluno quiser alguma, é só mandá-la na próxima
mensagem, como qualquer palavra nova."""

from __future__ import annotations

import logging

from app.domain.models import Entry, Expansion, Profile
from app.flows.base import Deps, bloq
from app.services.llm import LLMError

logger = logging.getLogger(__name__)

MAX_SUGESTOES = 3


async def sugestoes(d: Deps, entrada: Entry, perfil: Profile) -> list[Expansion]:
    existentes = [e.palavra for e in await bloq(d.repo.listar_entradas)]
    try:
        async with d.conversa.digitando():
            itens = await bloq(
                d.tutor.expansions, entrada.palavra, entrada.sentido, perfil.nivel, existentes
            )
    except LLMError:
        # A palavra já está salva; só não há sugestões desta vez.
        logger.warning("sem sugestões para %s", entrada.slug, exc_info=True)
        return []
    return itens[:MAX_SUGESTOES]
