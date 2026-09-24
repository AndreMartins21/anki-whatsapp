"""Rodízio da marcação na revisão em grupo (M17, ADR-0020): função pura, sem I/O.

Quem foi marcado há mais tempo (ou nunca) vem primeiro; empates se resolvem por sorteio; e ninguém é
marcado duas vezes seguidas se houver outro aluno. Assim as palavras se distribuem entre os alunos
com o tempo, sem ninguém dominar as respostas.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

_NUNCA = datetime.min.replace(tzinfo=UTC)


@dataclass(frozen=True)
class Candidato:
    numero: str
    marcado_em: datetime | None  # `None` = nunca foi marcado


def _sortear(itens: Sequence[Candidato]) -> Candidato:
    return random.choice(itens)  # noqa: S311 — só um desempate, sem fim criptográfico


def escolher(
    candidatos: Sequence[Candidato],
    *,
    excluir: str | None = None,
    sortear: Callable[[Sequence[Candidato]], Candidato] = _sortear,
) -> str | None:
    """O número de quem marcar, ou `None` sem candidatos. `excluir` é o último marcado: sai da
    disputa, a menos que seja o único aluno."""
    if not candidatos:
        return None
    disputa = [c for c in candidatos if c.numero != excluir] or list(candidatos)
    mais_antigo = min((c.marcado_em or _NUNCA) for c in disputa)
    empatados = [c for c in disputa if (c.marcado_em or _NUNCA) == mais_antigo]
    return sortear(empatados).numero
