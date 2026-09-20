"""Máquina de estados da conversa (seção 5.1) como função pura (ADR-0004).

`transicionar` só decide: devolve o próximo estado e a ação que os fluxos (M4) devem executar.
Não chama LLM, repositório nem canal.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from app.domain.choices import (
    MENU_APOS_EXEMPLOS,
    MENU_ESCOLHA_GUIADO,
    MENU_ESCOLHA_PRODUCAO,
    MENU_NOVA_PALAVRA,
    MENU_PRATICAR_EXPANSAO,
    MENU_PROXIMO,
    Menu,
    contem_palavra_alvo,
    eh_pular,
    parse_escolha,
    parse_lista_numeros,
    parse_numero,
    so_numeros,
)
from app.domain.models import Estado, ModoPratica

SESSAO_EXPIRA_APOS = timedelta(hours=3)
MAX_PALAVRAS_PALAVRA_NOVA = 4


class Acao(StrEnum):
    EXPLICAR = "EXPLICAR"
    ESCOLHER_SENTIDO = "ESCOLHER_SENTIDO"
    PEDIR_FRASE = "PEDIR_FRASE"
    GERAR_EXEMPLOS = "GERAR_EXEMPLOS"
    SALVAR = "SALVAR"
    AVALIAR = "AVALIAR"
    PERGUNTAR_NOVA_PALAVRA = "PERGUNTAR_NOVA_PALAVRA"
    SALVAR_E_EXPLICAR_NOVA = "SALVAR_E_EXPLICAR_NOVA"
    AVALIAR_FRASE_PENDENTE = "AVALIAR_FRASE_PENDENTE"
    CRIAR_EXPANSOES = "CRIAR_EXPANSOES"
    PRATICAR_EXPANSAO_AGORA = "PRATICAR_EXPANSAO_AGORA"
    ENCERRAR = "ENCERRAR"
    REENVIAR_MENU = "REENVIAR_MENU"


@dataclass(frozen=True)
class Contexto:
    """O que a decisão precisa saber e que não está no texto nem no estado."""

    palavra_alvo: str | None
    n_sentidos: int = 0
    n_expansoes: int = 0
    modo: ModoPratica = "guiado"


@dataclass(frozen=True)
class Transicao:
    """`estado` é o estado depois da ação; `None` quando depende do resultado dela (explicar
    uma palavra cai em `AWAIT_SENSE` ou no menu, conforme `estado_apos_explicar`)."""

    estado: Estado | None
    acao: Acao
    argumento: str | int | tuple[int, ...] | None = None


def estado_apos_definir_sentido(modo: ModoPratica) -> Estado:
    return Estado.AWAIT_SENTENCE if modo == "producao_primeiro" else Estado.AWAIT_CHOICE


def estado_apos_explicar(precisa_escolher_sentido: bool, modo: ModoPratica) -> Estado:
    if precisa_escolher_sentido:
        return Estado.AWAIT_SENSE
    return estado_apos_definir_sentido(modo)


def expirou(atualizado_em: datetime, agora: datetime) -> bool:
    """Sessão parada há mais de 3 horas volta para IDLE (o fluxo salva o que houver)."""
    return agora - atualizado_em > SESSAO_EXPIRA_APOS


def transicionar(estado: Estado, texto: str, ctx: Contexto) -> Transicao:
    texto = texto.strip()
    match estado:
        case Estado.IDLE:
            return Transicao(None, Acao.EXPLICAR, texto)
        case Estado.AWAIT_SENSE:
            return _await_sense(texto, ctx)
        case Estado.AWAIT_CHOICE:
            return _menu_com_frase_direta(estado, texto, ctx, MENU_ESCOLHA_GUIADO, _CHOICE)
        case Estado.AWAIT_SENTENCE:
            return _await_sentence(texto, ctx)
        case Estado.AWAIT_NEXT:
            return _menu_com_frase_direta(estado, texto, ctx, MENU_PROXIMO, _NEXT)
        case Estado.AWAIT_AFTER_EXAMPLES:
            return _menu_com_frase_direta(estado, texto, ctx, MENU_APOS_EXEMPLOS, _AFTER_EXAMPLES)
        case Estado.AWAIT_NEW_WORD:
            return _await_new_word(texto)
        case Estado.OFFER_EXPANSION:
            return _offer_expansion(texto, ctx)
        case Estado.AWAIT_EXPANSION_PRACTICE:
            return _await_expansion_practice(texto)


_CHOICE = {
    1: Transicao(Estado.AWAIT_SENTENCE, Acao.PEDIR_FRASE),
    2: Transicao(Estado.AWAIT_AFTER_EXAMPLES, Acao.GERAR_EXEMPLOS),
    3: Transicao(Estado.OFFER_EXPANSION, Acao.SALVAR),
}
_NEXT = _CHOICE
_AFTER_EXAMPLES = {
    1: Transicao(Estado.AWAIT_SENTENCE, Acao.PEDIR_FRASE),
    2: Transicao(Estado.OFFER_EXPANSION, Acao.SALVAR),
}
_PRODUCAO = {
    1: Transicao(Estado.AWAIT_AFTER_EXAMPLES, Acao.GERAR_EXEMPLOS),
    2: Transicao(Estado.OFFER_EXPANSION, Acao.SALVAR),
}


def _menu_com_frase_direta(
    estado: Estado,
    texto: str,
    ctx: Contexto,
    menu: Menu,
    resultados: dict[int, Transicao],
) -> Transicao:
    opcao = parse_escolha(texto, menu)
    if opcao is not None:
        return resultados[opcao]
    return _texto_livre(estado, texto, ctx, pode_avaliar=True)


def _await_sentence(texto: str, ctx: Contexto) -> Transicao:
    if ctx.modo == "producao_primeiro":
        opcao = parse_escolha(texto, MENU_ESCOLHA_PRODUCAO)
        if opcao is not None:
            return _PRODUCAO[opcao]
    if so_numeros(texto):
        return Transicao(Estado.AWAIT_SENTENCE, Acao.REENVIAR_MENU)
    if _parece_palavra_nova(texto, ctx):
        return Transicao(Estado.AWAIT_NEW_WORD, Acao.PERGUNTAR_NOVA_PALAVRA, texto)
    return Transicao(Estado.AWAIT_NEXT, Acao.AVALIAR, texto)


def _await_sense(texto: str, ctx: Contexto) -> Transicao:
    numero = parse_numero(texto, ctx.n_sentidos)
    if numero is not None:
        return Transicao(estado_apos_definir_sentido(ctx.modo), Acao.ESCOLHER_SENTIDO, numero)
    return _texto_livre(Estado.AWAIT_SENSE, texto, ctx, pode_avaliar=False)


def _await_new_word(texto: str) -> Transicao:
    opcao = parse_escolha(texto, MENU_NOVA_PALAVRA)
    if opcao == 1:
        return Transicao(None, Acao.SALVAR_E_EXPLICAR_NOVA)
    if opcao == 2:
        return Transicao(Estado.AWAIT_NEXT, Acao.AVALIAR_FRASE_PENDENTE)
    return Transicao(Estado.AWAIT_NEW_WORD, Acao.REENVIAR_MENU)


def _offer_expansion(texto: str, ctx: Contexto) -> Transicao:
    if eh_pular(texto):
        return Transicao(Estado.IDLE, Acao.ENCERRAR)
    numeros = parse_lista_numeros(texto, ctx.n_expansoes)
    if numeros is not None:
        return Transicao(Estado.AWAIT_EXPANSION_PRACTICE, Acao.CRIAR_EXPANSOES, tuple(numeros))
    return Transicao(Estado.OFFER_EXPANSION, Acao.REENVIAR_MENU)


def _await_expansion_practice(texto: str) -> Transicao:
    opcao = parse_escolha(texto, MENU_PRATICAR_EXPANSAO)
    if opcao == 1:
        return Transicao(None, Acao.PRATICAR_EXPANSAO_AGORA)
    if opcao == 2:
        return Transicao(Estado.IDLE, Acao.ENCERRAR)
    return Transicao(Estado.AWAIT_EXPANSION_PRACTICE, Acao.REENVIAR_MENU)


def _parece_palavra_nova(texto: str, ctx: Contexto) -> bool:
    contem_alvo = ctx.palavra_alvo is not None and contem_palavra_alvo(texto, ctx.palavra_alvo)
    return not contem_alvo and len(texto.split()) <= MAX_PALAVRAS_PALAVRA_NOVA


def _texto_livre(estado: Estado, texto: str, ctx: Contexto, *, pode_avaliar: bool) -> Transicao:
    """Texto que não é uma opção válida num estado que espera número (seção 5.1, "Regras")."""
    if so_numeros(texto):
        return Transicao(estado, Acao.REENVIAR_MENU)
    if pode_avaliar and ctx.palavra_alvo and contem_palavra_alvo(texto, ctx.palavra_alvo):
        return Transicao(Estado.AWAIT_NEXT, Acao.AVALIAR, texto)
    if _parece_palavra_nova(texto, ctx):
        return Transicao(Estado.AWAIT_NEW_WORD, Acao.PERGUNTAR_NOVA_PALAVRA, texto)
    return Transicao(estado, Acao.REENVIAR_MENU)
