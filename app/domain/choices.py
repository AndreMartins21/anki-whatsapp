"""Parser de escolhas numéricas (seção 5.1) e detecção heurística da palavra-alvo.

Todas as escolhas são por número, mas aceitamos variações (`1`, `1.`, `um`, `escrever`). O mesmo
texto pode significar opções diferentes conforme o menu (`escrever` é 1 no menu inicial e a
opção 1 do menu seguinte é `outra frase`), por isso cada menu declara os seus apelidos.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping

Menu = Mapping[int, tuple[str, ...]]

MENU_ESCOLHA_GUIADO: Menu = {
    1: ("escrever", "escrever uma frase", "escrever frase", "frase"),
    2: ("exemplo", "exemplos", "ver exemplos", "ver exemplo"),
    3: ("salvar", "so salvar"),
}
MENU_ESCOLHA_PRODUCAO: Menu = {
    1: ("exemplo", "exemplos", "me da um exemplo", "ver exemplos"),
    2: ("salvar", "so salvar"),
}
MENU_PROXIMO: Menu = {
    1: ("outra frase", "outra", "escrever"),
    2: ("exemplo", "exemplos", "ver exemplos"),
    3: ("concluir", "salvar"),
}
MENU_APOS_EXEMPLOS: Menu = {
    1: ("escrever", "escrever uma frase", "frase"),
    2: ("concluir", "salvar"),
}
MENU_NOVA_PALAVRA: Menu = {
    1: ("praticar", "praticar agora", "agora", "sim"),
    2: ("minha frase", "era minha frase", "frase"),
}
MENU_PRATICAR_EXPANSAO: Menu = {
    1: ("praticar", "praticar agora", "agora"),
    2: ("depois", "mais tarde"),
}

_NUMEROS_POR_EXTENSO = {
    "zero": 0,
    "um": 1,
    "uma": 1,
    "dois": 2,
    "duas": 2,
    "tres": 3,
    "quatro": 4,
    "cinco": 5,
}
_PULAR = {"0", "zero", "pular", "nenhuma", "nenhum", "nada"}


def normalizar(texto: str) -> str:
    """Minúsculas, sem acento, emoji-teclado ou pontuação; espaços colapsados."""
    decomposto = unicodedata.normalize("NFKD", texto)
    sem_marcas = "".join(c for c in decomposto if not unicodedata.category(c).startswith("M"))
    so_palavras = re.sub(r"[^\w\s]", " ", sem_marcas.lower())
    return " ".join(so_palavras.split())


def _como_numero(token: str) -> int | None:
    if token.isdigit():
        return int(token)
    return _NUMEROS_POR_EXTENSO.get(token)


def parse_escolha(texto: str, menu: Menu) -> int | None:
    """Número (ou apelido) -> opção do menu; `None` se não for uma opção válida."""
    normalizado = normalizar(texto)
    numero = _como_numero(normalizado)
    if numero is not None:
        return numero if numero in menu else None
    for opcao, apelidos in menu.items():
        if normalizado in apelidos:
            return opcao
    return None


def parse_numero(texto: str, maximo: int) -> int | None:
    """Um número de 1 a `maximo` (menu de sentidos, de tamanho variável)."""
    numero = _como_numero(normalizar(texto))
    return numero if numero is not None and 1 <= numero <= maximo else None


def parse_lista_numeros(texto: str, maximo: int) -> list[int] | None:
    """`1,3`, `1 3`, `1 e 3` -> `[1, 3]` (sem repetição, na ordem dada). Um item inválido anula tudo."""
    tokens = [t for t in normalizar(texto).split() if t != "e"]
    if not tokens:
        return None
    numeros: list[int] = []
    for token in tokens:
        numero = _como_numero(token)
        if numero is None or not 1 <= numero <= maximo:
            return None
        if numero not in numeros:
            numeros.append(numero)
    return numeros


def eh_pular(texto: str) -> bool:
    return normalizar(texto) in _PULAR


def so_numeros(texto: str) -> bool:
    """Só números/`e`: nunca é uma palavra ou frase, mesmo quando não é uma opção válida."""
    tokens = normalizar(texto).split()
    return any(_como_numero(t) is not None for t in tokens) and all(
        _como_numero(t) is not None or t == "e" for t in tokens
    )


def _flexoes(palavra: str) -> set[str]:
    formas = {
        palavra,
        palavra + "s",
        palavra + "es",
        palavra + "ed",
        palavra + "ing",
        palavra + "ly",
    }
    if palavra.endswith("e"):
        formas |= {palavra + "d", palavra[:-1] + "ing"}
    if len(palavra) > 1 and palavra.endswith("y") and palavra[-2] not in "aeiou":
        radical = palavra[:-1]
        formas |= {radical + "ies", radical + "ied", radical + "ily"}
    if len(palavra) > 1 and palavra[-1] not in "aeiouwxy":
        formas |= {palavra + palavra[-1] + "ed", palavra + palavra[-1] + "ing"}
    return formas


def contem_palavra_alvo(texto: str, palavra: str) -> bool:
    """Heurística: a palavra (ou expressão, com as palavras em ordem) aparece, com flexões regulares.

    Formas irregulares (`gave`/`give`) não são reconhecidas aqui — a avaliação do LLM
    (`usa_palavra_alvo`) é quem decide de fato (ver ADR-0004).
    """
    tokens = normalizar(texto).split()
    posicao = 0
    for parte in normalizar(palavra).split():
        formas = _flexoes(parte)
        try:
            achado = next(i for i in range(posicao, len(tokens)) if tokens[i] in formas)
        except StopIteration:
            return False
        posicao = achado + 1
    return bool(normalizar(palavra))
