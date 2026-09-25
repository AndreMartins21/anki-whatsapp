"""Máquina de estados da conversa (seção 5.1) como função pura (ADR-0004, ADR-0009).

`transicionar` só decide: devolve o próximo estado e a ação que os fluxos (M4/M9/M10) devem
executar. Não chama LLM, repositório nem canal — mesmo o roteamento por IA (`Acao.ROTEAR`), a
revisão espaçada (`Acao.RESPONDER_REVISAO`) e a prática com música (M13, `Acao.RESPONDER_VERSO`)
são decididos aqui como "isto precisa de IA" e executados pelo `Router`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from app.domain.choices import (
    MENU_ACOES,
    eh_pular,
    eh_sair,
    eh_todos,
    parse_escolha,
    so_numeros,
)
from app.domain.models import Estado

SESSAO_EXPIRA_APOS = timedelta(hours=3)


class Acao(StrEnum):
    EXPLICAR = "EXPLICAR"
    GERAR_EXEMPLOS = "GERAR_EXEMPLOS"
    GERAR_SINONIMOS = "GERAR_SINONIMOS"
    SALVAR = "SALVAR"
    PULAR = "PULAR"
    IGNORAR = "IGNORAR"
    ROTEAR = "ROTEAR"
    RESPONDER_REVISAO = "RESPONDER_REVISAO"
    ENCERRAR_REVISAO = "ENCERRAR_REVISAO"
    BUSCAR_MUSICA = "BUSCAR_MUSICA"
    ESCOLHER_MUSICA = "ESCOLHER_MUSICA"
    CANCELAR_MUSICA = "CANCELAR_MUSICA"
    RESPONDER_VERSO = "RESPONDER_VERSO"
    ENCERRAR_MUSICA = "ENCERRAR_MUSICA"
    SALVAR_EXPRESSOES = "SALVAR_EXPRESSOES"
    DESCARTAR_EXPRESSOES = "DESCARTAR_EXPRESSOES"


@dataclass(frozen=True)
class Transicao:
    """`estado` é o estado depois da ação."""

    estado: Estado
    acao: Acao
    argumento: str | None = None


def expirou(atualizado_em: datetime, agora: datetime) -> bool:
    """Sessão parada há mais de 3 horas volta para IDLE (o fluxo salva o que houver)."""
    return agora - atualizado_em > SESSAO_EXPIRA_APOS


_ACAO_DO_MENU = {
    1: Acao.GERAR_EXEMPLOS,
    2: Acao.GERAR_SINONIMOS,
    3: Acao.SALVAR,
    4: Acao.IGNORAR,
}
_ACAO_QUE_ENCERRA = {Acao.SALVAR, Acao.IGNORAR}


def transicionar(estado: Estado, texto: str) -> Transicao:
    texto = texto.strip()
    match estado:
        case Estado.IDLE:
            return Transicao(Estado.AWAIT_ACTION, Acao.EXPLICAR, texto)
        case Estado.AWAIT_ACTION:
            return _await_action(texto)
        case Estado.REVIEWING:
            return _reviewing(texto)
        case Estado.SONG_PICKING:
            return _song_picking(texto)
        case Estado.SONG_PRACTICE:
            return _song_practice(texto)
        case Estado.SONG_SAVING:
            return _song_saving(texto)


def _await_action(texto: str) -> Transicao:
    opcao = parse_escolha(texto, MENU_ACOES)
    if opcao is not None:
        acao = _ACAO_DO_MENU[opcao]
        estado = Estado.IDLE if acao in _ACAO_QUE_ENCERRA else Estado.AWAIT_ACTION
        return Transicao(estado, acao)
    if eh_pular(texto):
        return Transicao(Estado.IDLE, Acao.PULAR)
    return Transicao(Estado.AWAIT_ACTION, Acao.ROTEAR, texto)


def _reviewing(texto: str) -> Transicao:
    """Durante a revisão (seção 5.7), qualquer texto que não seja "sair" é a resposta do aluno
    para a palavra atual — sem roteamento por IA aqui, que só geraria ambiguidade e custo."""
    if eh_sair(texto):
        return Transicao(Estado.IDLE, Acao.ENCERRAR_REVISAO)
    return Transicao(Estado.REVIEWING, Acao.RESPONDER_REVISAO, texto)


def _song_picking(texto: str) -> Transicao:
    """Escolhendo entre músicas homônimas (seção 5.8): um número escolhe (o fluxo confere se está
    na lista), "sair" cancela e qualquer outro texto é uma nova busca."""
    if eh_sair(texto):
        return Transicao(Estado.IDLE, Acao.CANCELAR_MUSICA)
    if so_numeros(texto):
        return Transicao(Estado.SONG_PRACTICE, Acao.ESCOLHER_MUSICA, texto)
    return Transicao(Estado.SONG_PICKING, Acao.BUSCAR_MUSICA, texto)


def _song_practice(texto: str) -> Transicao:
    """Como na revisão: qualquer texto que não seja "sair" é a explicação do verso atual. Sair
    fecha com o resumo e a oferta de salvar (o fluxo decide se vai para SONG_SAVING)."""
    if eh_sair(texto):
        return Transicao(Estado.SONG_SAVING, Acao.ENCERRAR_MUSICA)
    return Transicao(Estado.SONG_PRACTICE, Acao.RESPONDER_VERSO, texto)


def _song_saving(texto: str) -> Transicao:
    """Oferta de salvar as expressões da música: números ou "all" salvam, "sair" descarta, e
    qualquer outro texto é o aluno seguindo em frente com uma palavra nova."""
    if eh_sair(texto):
        return Transicao(Estado.IDLE, Acao.DESCARTAR_EXPRESSOES)
    if so_numeros(texto) or eh_todos(texto):
        return Transicao(Estado.IDLE, Acao.SALVAR_EXPRESSOES, texto)
    return Transicao(Estado.AWAIT_ACTION, Acao.EXPLICAR, texto)
