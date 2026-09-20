"""Testes de app/domain/choices.py: parser de escolhas numéricas e detecção da palavra-alvo."""

from __future__ import annotations

import pytest

from app.domain.choices import (
    MENU_APOS_EXEMPLOS,
    MENU_ESCOLHA_GUIADO,
    MENU_ESCOLHA_PRODUCAO,
    MENU_NOVA_PALAVRA,
    MENU_PRATICAR_EXPANSAO,
    MENU_PROXIMO,
    contem_palavra_alvo,
    eh_pular,
    marcar_alvo,
    parse_escolha,
    parse_lista_numeros,
    parse_numero,
    so_numeros,
)


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("1", 1),
        ("1.", 1),
        ("1)", 1),
        (" 2 ", 2),
        ("um", 1),
        ("Um", 1),
        ("três", 3),
        ("1️⃣", 1),
        ("escrever", 1),
        ("Escrever uma frase", 1),
        ("ver exemplos", 2),
        ("só salvar", 3),
        ("so salvar", 3),
        ("4", None),
        ("stall", None),
        ("", None),
    ],
)
def test_menu_guiado_aceita_numero_e_variacoes(texto: str, esperado: int | None) -> None:
    assert parse_escolha(texto, MENU_ESCOLHA_GUIADO) == esperado


def test_mesma_palavra_muda_de_sentido_conforme_o_menu() -> None:
    assert parse_escolha("escrever", MENU_ESCOLHA_GUIADO) == 1
    assert parse_escolha("outra frase", MENU_PROXIMO) == 1
    assert parse_escolha("concluir", MENU_PROXIMO) == 3
    assert parse_escolha("concluir", MENU_APOS_EXEMPLOS) == 2
    assert parse_escolha("me dá um exemplo", MENU_ESCOLHA_PRODUCAO) == 1
    assert parse_escolha("praticar agora", MENU_NOVA_PALAVRA) == 1
    assert parse_escolha("era minha frase", MENU_NOVA_PALAVRA) == 2
    assert parse_escolha("depois", MENU_PRATICAR_EXPANSAO) == 2


@pytest.mark.parametrize(
    ("texto", "maximo", "esperado"),
    [("1", 3, 1), ("3", 3, 3), ("dois", 3, 2), ("4", 3, None), ("0", 3, None), ("x", 3, None)],
)
def test_parse_numero_respeita_o_maximo(texto: str, maximo: int, esperado: int | None) -> None:
    assert parse_numero(texto, maximo) == esperado


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("1,3", [1, 3]),
        ("1, 3", [1, 3]),
        ("1 3", [1, 3]),
        ("1 e 3", [1, 3]),
        ("3,1", [3, 1]),
        ("2", [2]),
        ("1,1,3", [1, 3]),
        ("1,9", None),  # fora do intervalo
        ("1,x", None),
        ("", None),
        ("0", None),
    ],
)
def test_parse_lista_numeros(texto: str, esperado: list[int] | None) -> None:
    assert parse_lista_numeros(texto, maximo=5) == esperado


@pytest.mark.parametrize("texto", ["0", "pular", "Pular", "nenhuma", "nenhum"])
def test_eh_pular(texto: str) -> None:
    assert eh_pular(texto) is True


def test_eh_pular_rejeita_o_resto() -> None:
    assert eh_pular("1") is False
    assert eh_pular("stall") is False


def test_so_numeros() -> None:
    assert so_numeros("7") is True
    assert so_numeros("1, 3") is True
    assert so_numeros("stall") is False
    assert so_numeros("") is False


@pytest.mark.parametrize(
    ("texto", "palavra"),
    [
        ("the talks stalled", "stall"),
        ("The talks STALLED.", "stall"),
        ("stalling again", "stall"),
        ("two stalls", "stall"),
        ("he stopped talking", "stop"),
        ("she is studying", "study"),
        ("it studies well", "study"),
        ("we decided to leave", "decide"),
        ("it's a lovely day", "love"),
        ("we are giving up early", "give up"),
        ("do not give it up", "give up"),
        ("she gives up easily", "give up"),
    ],
)
def test_contem_palavra_alvo_reconhece_flexoes_regulares(texto: str, palavra: str) -> None:
    assert contem_palavra_alvo(texto, palavra) is True


@pytest.mark.parametrize(
    ("texto", "palavra"),
    [
        ("I like coffee", "stall"),
        ("the installation failed", "stall"),  # substring não conta
        ("up we gave", "give up"),  # ordem importa
        ("just give", "give up"),
        ("", "stall"),
    ],
)
def test_contem_palavra_alvo_rejeita_o_que_nao_e_a_palavra(texto: str, palavra: str) -> None:
    assert contem_palavra_alvo(texto, palavra) is False


@pytest.mark.parametrize(
    ("frase", "palavra", "esperado"),
    [
        (
            "The negotiations stalled after the meeting.",
            "stall",
            "The negotiations [[stalled]] after the meeting.",
        ),
        ("Stalling again.", "stall", "[[Stalling]] again."),
        ("We had to give up early.", "give up", "We had to [[give up]] early."),
        ("Don't give it up now.", "give up", "Don't [[give it up]] now."),
        ("She is studying hard.", "study", "She is [[studying]] hard."),
        ("I like coffee.", "stall", None),
        ("The installation failed.", "stall", None),
        ("", "stall", None),
    ],
)
def test_marcar_alvo(frase: str, palavra: str, esperado: str | None) -> None:
    assert marcar_alvo(frase, palavra) == esperado
