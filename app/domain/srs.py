"""Revisão espaçada (M10, seção 5.7, ADR-0011): SM-2 simplificado, como função pura.

Igual à máquina de estados (ADR-0004), `reagendar` só decide: não lê nem grava nada. A nota
(`QualidadeRevisao`) vem do julgamento do LLM sobre a resposta do aluno (`Tutor.review`), não de
4 botões como no Anki de verdade — por isso "simplificado". O agendamento daqui é independente do
agendamento do próprio Anki (ver ADR-0011): exportar não sincroniza os dois.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.domain.models import Entry, QualidadeRevisao

FACILIDADE_MINIMA = 1.3
FACILIDADE_MAXIMA = 2.5

_AJUSTE_DE_FACILIDADE: dict[QualidadeRevisao, float] = {
    "de_novo": -0.20,
    "dificil": -0.15,
    "bom": 0.0,
    "facil": 0.15,
}


@dataclass(frozen=True)
class Agendamento:
    repeticoes: int
    intervalo_dias: float
    facilidade: float
    proxima_revisao: datetime
    lapsos: int


def _limitar_facilidade(valor: float) -> float:
    return max(FACILIDADE_MINIMA, min(FACILIDADE_MAXIMA, valor))


def reagendar(entrada: Entry, qualidade: QualidadeRevisao, agora: datetime) -> Agendamento:
    """O próximo agendamento de `entrada` depois de uma revisão com a nota `qualidade`.

    `de_novo`: reseta a repetição (intervalo 0 — vencido de novo já hoje) e conta um lapso; a
    palavra volta ao fim da fila *desta* sessão (decisão do fluxo, não daqui). `dificil`/`bom`/
    `facil`: cresce o intervalo (1 dia, depois 3, depois `intervalo * facilidade`), com `dificil`
    crescendo mais devagar e `facil` mais rápido. `facilidade` nunca sai de
    [`FACILIDADE_MINIMA`, `FACILIDADE_MAXIMA`].
    """
    facilidade = _limitar_facilidade(entrada.facilidade + _AJUSTE_DE_FACILIDADE[qualidade])

    if qualidade == "de_novo":
        return Agendamento(
            repeticoes=0,
            intervalo_dias=0.0,
            facilidade=facilidade,
            proxima_revisao=agora,
            lapsos=entrada.lapsos + 1,
        )

    if entrada.repeticoes == 0:
        intervalo = 1.0
    elif entrada.repeticoes == 1:
        intervalo = 3.0
    else:
        intervalo = entrada.intervalo_dias * facilidade

    if qualidade == "dificil":
        intervalo = max(1.0, intervalo * 0.8)
    elif qualidade == "facil":
        intervalo *= 1.3

    return Agendamento(
        repeticoes=entrada.repeticoes + 1,
        intervalo_dias=intervalo,
        facilidade=facilidade,
        proxima_revisao=agora + timedelta(days=intervalo),
        lapsos=entrada.lapsos,
    )


def vencida(entrada: Entry, agora: datetime) -> bool:
    """Cartão novo (nunca revisado) ou cuja `proxima_revisao` já passou."""
    return entrada.proxima_revisao is None or entrada.proxima_revisao <= agora
