"""Máquina de estados da conversa (seção 5.1) como função pura (ADR-0004, ADR-0009).

`transicionar` só decide: devolve o próximo estado e a ação que os fluxos (M4/M9) devem executar.
Não chama LLM, repositório nem canal — mesmo o roteamento por IA (`Acao.ROTEAR`) é decidido aqui
como "preciso rotear" e executado pelo `Router`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from app.domain.choices import MENU_ACOES, parse_escolha
from app.domain.models import Estado

SESSAO_EXPIRA_APOS = timedelta(hours=3)


class Acao(StrEnum):
    EXPLICAR = "EXPLICAR"
    GERAR_EXEMPLOS = "GERAR_EXEMPLOS"
    GERAR_SINONIMOS = "GERAR_SINONIMOS"
    SALVAR = "SALVAR"
    ROTEAR = "ROTEAR"


@dataclass(frozen=True)
class Transicao:
    """`estado` é o estado depois da ação."""

    estado: Estado
    acao: Acao
    argumento: str | None = None


def expirou(atualizado_em: datetime, agora: datetime) -> bool:
    """Sessão parada há mais de 3 horas volta para IDLE (o fluxo salva o que houver)."""
    return agora - atualizado_em > SESSAO_EXPIRA_APOS


_ACAO_DO_MENU = {1: Acao.GERAR_EXEMPLOS, 2: Acao.GERAR_SINONIMOS, 3: Acao.SALVAR}


def transicionar(estado: Estado, texto: str) -> Transicao:
    texto = texto.strip()
    match estado:
        case Estado.IDLE:
            return Transicao(Estado.AWAIT_ACTION, Acao.EXPLICAR, texto)
        case Estado.AWAIT_ACTION:
            return _await_action(texto)


def _await_action(texto: str) -> Transicao:
    opcao = parse_escolha(texto, MENU_ACOES)
    if opcao is not None:
        acao = _ACAO_DO_MENU[opcao]
        estado = Estado.IDLE if acao is Acao.SALVAR else Estado.AWAIT_ACTION
        return Transicao(estado, acao)
    return Transicao(Estado.AWAIT_ACTION, Acao.ROTEAR, texto)
