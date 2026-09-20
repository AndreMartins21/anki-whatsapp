"""Testes de app/domain/state.py — todas as transições da seção 5.1, incluindo os atalhos."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.models import Estado
from app.domain.state import (
    Acao,
    Contexto,
    Transicao,
    estado_apos_explicar,
    expirou,
    transicionar,
)

CTX = Contexto(palavra_alvo="stall", n_sentidos=3, n_expansoes=4)
CTX_PRODUCAO = Contexto(palavra_alvo="stall", n_sentidos=3, n_expansoes=4, modo="producao_primeiro")

# (estado, texto, transição esperada)
TRANSICOES = [
    # IDLE: qualquer texto é uma palavra/expressão a explicar; o estado final decide o fluxo.
    (Estado.IDLE, "stall", Transicao(None, Acao.EXPLICAR, "stall")),
    (
        Estado.IDLE,
        "stall | the talks stalled",
        Transicao(None, Acao.EXPLICAR, "stall | the talks stalled"),
    ),
    # AWAIT_SENSE
    (Estado.AWAIT_SENSE, "2", Transicao(Estado.AWAIT_CHOICE, Acao.ESCOLHER_SENTIDO, 2)),
    (Estado.AWAIT_SENSE, "três", Transicao(Estado.AWAIT_CHOICE, Acao.ESCOLHER_SENTIDO, 3)),
    (Estado.AWAIT_SENSE, "9", Transicao(Estado.AWAIT_SENSE, Acao.REENVIAR_MENU)),
    (
        Estado.AWAIT_SENSE,
        "hedge",
        Transicao(Estado.AWAIT_NEW_WORD, Acao.PERGUNTAR_NOVA_PALAVRA, "hedge"),
    ),
    (
        Estado.AWAIT_SENSE,
        "the talks stalled again today please",
        Transicao(Estado.AWAIT_SENSE, Acao.REENVIAR_MENU),
    ),
    # AWAIT_CHOICE
    (Estado.AWAIT_CHOICE, "1", Transicao(Estado.AWAIT_SENTENCE, Acao.PEDIR_FRASE)),
    (Estado.AWAIT_CHOICE, "escrever", Transicao(Estado.AWAIT_SENTENCE, Acao.PEDIR_FRASE)),
    (Estado.AWAIT_CHOICE, "2", Transicao(Estado.AWAIT_AFTER_EXAMPLES, Acao.GERAR_EXEMPLOS)),
    (Estado.AWAIT_CHOICE, "3", Transicao(Estado.OFFER_EXPANSION, Acao.SALVAR)),
    (Estado.AWAIT_CHOICE, "só salvar", Transicao(Estado.OFFER_EXPANSION, Acao.SALVAR)),
    (
        Estado.AWAIT_CHOICE,
        "the talks stalled",
        Transicao(Estado.AWAIT_NEXT, Acao.AVALIAR, "the talks stalled"),
    ),
    (
        Estado.AWAIT_CHOICE,
        "hedge",
        Transicao(Estado.AWAIT_NEW_WORD, Acao.PERGUNTAR_NOVA_PALAVRA, "hedge"),
    ),
    (Estado.AWAIT_CHOICE, "7", Transicao(Estado.AWAIT_CHOICE, Acao.REENVIAR_MENU)),
    (
        Estado.AWAIT_CHOICE,
        "não entendi nada do que você disse agora",
        Transicao(Estado.AWAIT_CHOICE, Acao.REENVIAR_MENU),
    ),
    # AWAIT_SENTENCE
    (
        Estado.AWAIT_SENTENCE,
        "The project stalled because of budget",
        Transicao(Estado.AWAIT_NEXT, Acao.AVALIAR, "The project stalled because of budget"),
    ),
    (
        Estado.AWAIT_SENTENCE,
        "I like coffee very much every morning",
        Transicao(Estado.AWAIT_NEXT, Acao.AVALIAR, "I like coffee very much every morning"),
    ),
    (
        Estado.AWAIT_SENTENCE,
        "hedge",
        Transicao(Estado.AWAIT_NEW_WORD, Acao.PERGUNTAR_NOVA_PALAVRA, "hedge"),
    ),
    (Estado.AWAIT_SENTENCE, "stalls", Transicao(Estado.AWAIT_NEXT, Acao.AVALIAR, "stalls")),
    (Estado.AWAIT_SENTENCE, "1", Transicao(Estado.AWAIT_SENTENCE, Acao.REENVIAR_MENU)),
    # AWAIT_NEXT
    (Estado.AWAIT_NEXT, "1", Transicao(Estado.AWAIT_SENTENCE, Acao.PEDIR_FRASE)),
    (Estado.AWAIT_NEXT, "outra frase", Transicao(Estado.AWAIT_SENTENCE, Acao.PEDIR_FRASE)),
    (Estado.AWAIT_NEXT, "2", Transicao(Estado.AWAIT_AFTER_EXAMPLES, Acao.GERAR_EXEMPLOS)),
    (Estado.AWAIT_NEXT, "3", Transicao(Estado.OFFER_EXPANSION, Acao.SALVAR)),
    (Estado.AWAIT_NEXT, "concluir", Transicao(Estado.OFFER_EXPANSION, Acao.SALVAR)),
    (
        Estado.AWAIT_NEXT,
        "they stalled the talks",
        Transicao(Estado.AWAIT_NEXT, Acao.AVALIAR, "they stalled the talks"),
    ),
    (
        Estado.AWAIT_NEXT,
        "hedge",
        Transicao(Estado.AWAIT_NEW_WORD, Acao.PERGUNTAR_NOVA_PALAVRA, "hedge"),
    ),
    (Estado.AWAIT_NEXT, "4", Transicao(Estado.AWAIT_NEXT, Acao.REENVIAR_MENU)),
    # AWAIT_AFTER_EXAMPLES
    (Estado.AWAIT_AFTER_EXAMPLES, "1", Transicao(Estado.AWAIT_SENTENCE, Acao.PEDIR_FRASE)),
    (Estado.AWAIT_AFTER_EXAMPLES, "2", Transicao(Estado.OFFER_EXPANSION, Acao.SALVAR)),
    (Estado.AWAIT_AFTER_EXAMPLES, "concluir", Transicao(Estado.OFFER_EXPANSION, Acao.SALVAR)),
    (
        Estado.AWAIT_AFTER_EXAMPLES,
        "the deal stalled",
        Transicao(Estado.AWAIT_NEXT, Acao.AVALIAR, "the deal stalled"),
    ),
    (
        Estado.AWAIT_AFTER_EXAMPLES,
        "hedge",
        Transicao(Estado.AWAIT_NEW_WORD, Acao.PERGUNTAR_NOVA_PALAVRA, "hedge"),
    ),
    (Estado.AWAIT_AFTER_EXAMPLES, "3", Transicao(Estado.AWAIT_AFTER_EXAMPLES, Acao.REENVIAR_MENU)),
    # AWAIT_NEW_WORD ("1 praticar X agora (salvo a anterior) · 2 era minha frase")
    (Estado.AWAIT_NEW_WORD, "1", Transicao(None, Acao.SALVAR_E_EXPLICAR_NOVA)),
    (Estado.AWAIT_NEW_WORD, "2", Transicao(Estado.AWAIT_NEXT, Acao.AVALIAR_FRASE_PENDENTE)),
    (
        Estado.AWAIT_NEW_WORD,
        "era minha frase",
        Transicao(Estado.AWAIT_NEXT, Acao.AVALIAR_FRASE_PENDENTE),
    ),
    (Estado.AWAIT_NEW_WORD, "talvez", Transicao(Estado.AWAIT_NEW_WORD, Acao.REENVIAR_MENU)),
    # OFFER_EXPANSION
    (
        Estado.OFFER_EXPANSION,
        "1,3",
        Transicao(Estado.AWAIT_EXPANSION_PRACTICE, Acao.CRIAR_EXPANSOES, (1, 3)),
    ),
    (
        Estado.OFFER_EXPANSION,
        "2",
        Transicao(Estado.AWAIT_EXPANSION_PRACTICE, Acao.CRIAR_EXPANSOES, (2,)),
    ),
    (Estado.OFFER_EXPANSION, "0", Transicao(Estado.IDLE, Acao.ENCERRAR)),
    (Estado.OFFER_EXPANSION, "pular", Transicao(Estado.IDLE, Acao.ENCERRAR)),
    (Estado.OFFER_EXPANSION, "1,9", Transicao(Estado.OFFER_EXPANSION, Acao.REENVIAR_MENU)),
    (Estado.OFFER_EXPANSION, "quero todas", Transicao(Estado.OFFER_EXPANSION, Acao.REENVIAR_MENU)),
    # AWAIT_EXPANSION_PRACTICE ("1 praticar agora · 2 depois")
    (Estado.AWAIT_EXPANSION_PRACTICE, "1", Transicao(None, Acao.PRATICAR_EXPANSAO_AGORA)),
    (Estado.AWAIT_EXPANSION_PRACTICE, "2", Transicao(Estado.IDLE, Acao.ENCERRAR)),
    (Estado.AWAIT_EXPANSION_PRACTICE, "depois", Transicao(Estado.IDLE, Acao.ENCERRAR)),
    (
        Estado.AWAIT_EXPANSION_PRACTICE,
        "3",
        Transicao(Estado.AWAIT_EXPANSION_PRACTICE, Acao.REENVIAR_MENU),
    ),
]


@pytest.mark.parametrize(("estado", "texto", "esperada"), TRANSICOES)
def test_transicoes_do_modo_guiado(estado: Estado, texto: str, esperada: Transicao) -> None:
    assert transicionar(estado, texto, CTX) == esperada


TRANSICOES_PRODUCAO = [
    # No modo `producao_primeiro` o menu vira "1 me dá um exemplo · 2 só salvar".
    (Estado.AWAIT_SENTENCE, "1", Transicao(Estado.AWAIT_AFTER_EXAMPLES, Acao.GERAR_EXEMPLOS)),
    (
        Estado.AWAIT_SENTENCE,
        "me dá um exemplo",
        Transicao(Estado.AWAIT_AFTER_EXAMPLES, Acao.GERAR_EXEMPLOS),
    ),
    (Estado.AWAIT_SENTENCE, "2", Transicao(Estado.OFFER_EXPANSION, Acao.SALVAR)),
    (Estado.AWAIT_SENTENCE, "só salvar", Transicao(Estado.OFFER_EXPANSION, Acao.SALVAR)),
    (
        Estado.AWAIT_SENTENCE,
        "the talks stalled",
        Transicao(Estado.AWAIT_NEXT, Acao.AVALIAR, "the talks stalled"),
    ),
    (Estado.AWAIT_SENTENCE, "3", Transicao(Estado.AWAIT_SENTENCE, Acao.REENVIAR_MENU)),
    (Estado.AWAIT_SENSE, "1", Transicao(Estado.AWAIT_SENTENCE, Acao.ESCOLHER_SENTIDO, 1)),
]


@pytest.mark.parametrize(("estado", "texto", "esperada"), TRANSICOES_PRODUCAO)
def test_transicoes_do_modo_producao_primeiro(
    estado: Estado, texto: str, esperada: Transicao
) -> None:
    assert transicionar(estado, texto, CTX_PRODUCAO) == esperada


def test_palavra_nova_curta_com_alvo_ausente_so_dispara_a_pergunta_ate_4_palavras() -> None:
    quatro = transicionar(Estado.AWAIT_CHOICE, "give up on it", CTX)
    cinco = transicionar(Estado.AWAIT_CHOICE, "give up on it now", CTX)

    assert quatro.acao is Acao.PERGUNTAR_NOVA_PALAVRA
    assert cinco.acao is Acao.REENVIAR_MENU


def test_sem_palavra_alvo_no_contexto_nunca_avalia() -> None:
    ctx = Contexto(palavra_alvo=None)

    assert transicionar(Estado.AWAIT_CHOICE, "the talks stalled", ctx).acao is not Acao.AVALIAR


@pytest.mark.parametrize(
    ("precisa_escolher_sentido", "modo", "esperado"),
    [
        (True, "guiado", Estado.AWAIT_SENSE),
        (True, "producao_primeiro", Estado.AWAIT_SENSE),
        (False, "guiado", Estado.AWAIT_CHOICE),
        (False, "producao_primeiro", Estado.AWAIT_SENTENCE),
    ],
)
def test_estado_apos_explicar(precisa_escolher_sentido: bool, modo: str, esperado: Estado) -> None:
    assert estado_apos_explicar(precisa_escolher_sentido, modo) is esperado  # type: ignore[arg-type]


def test_sessao_expira_depois_de_3_horas_parada() -> None:
    agora = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)

    assert expirou(agora - timedelta(hours=3, minutes=1), agora) is True
    assert expirou(agora - timedelta(hours=2, minutes=59), agora) is False
