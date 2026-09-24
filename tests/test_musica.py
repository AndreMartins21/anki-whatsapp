"""Funções puras da prática com música (M13, seção 5.8). As letras aqui são inventadas — nunca
use letra de música real em teste, fixture ou eval (ADR-0016)."""

from __future__ import annotations

from app.domain.musica import (
    MAX_VERSOS,
    Musica,
    eh_ingles,
    escolher_candidatas,
    extrair_versos,
    filtrar_expressoes,
    separar_titulo_e_artista,
)

LETRA_INVENTADA = """[Verse 1]
I left my keys beside the kitchen door
The morning bus is running late once more

[Chorus]
Hold on, the city never sleeps
Hold on, the city never sleeps
Oh oh oh

I wrote your name on a paper plane
(x2)
Hold on, the city never sleeps
"""

LETRA_PT = """Deixei a chave na porta da cozinha
O ônibus da manhã atrasou de novo
Segura firme que a cidade não dorme
"""


def _musica(id_: int, titulo: str, artista: str, letra: str | None = LETRA_INVENTADA) -> Musica:
    return Musica(id=id_, titulo=titulo, artista=artista, letra=letra)


# --- extrair_versos ---


def test_extrai_versos_sem_marcacoes_linhas_vazias_nem_repeticoes() -> None:
    assert extrair_versos(LETRA_INVENTADA) == [
        "I left my keys beside the kitchen door",
        "The morning bus is running late once more",
        "Hold on, the city never sleeps",
        "I wrote your name on a paper plane",
    ]


def test_repeticao_ignora_caixa_e_pontuacao() -> None:
    letra = "Hold on, the city never sleeps\nhold on the city never sleeps!\nNew line here now"
    assert extrair_versos(letra) == ["Hold on, the city never sleeps", "New line here now"]


def test_pula_versos_de_uma_palavra_so_e_so_interjeicoes() -> None:
    letra = "Yeah\nOoh yeah yeah\nla la la\nWe keep on walking home"
    assert extrair_versos(letra) == ["We keep on walking home"]


def test_limita_o_numero_de_versos() -> None:
    letra = "\n".join(f"line number {i} goes here" for i in range(MAX_VERSOS + 10))
    versos = extrair_versos(letra)
    assert len(versos) == MAX_VERSOS
    assert versos[0] == "line number 0 goes here"


# --- eh_ingles ---


def test_letra_em_ingles_e_ingles() -> None:
    assert eh_ingles(LETRA_INVENTADA)


def test_letra_em_portugues_nao_e_ingles() -> None:
    assert not eh_ingles(LETRA_PT)


def test_letra_vazia_nao_e_ingles() -> None:
    assert not eh_ingles("")


# --- separar_titulo_e_artista ---


def test_separa_titulo_e_artista_pelo_hifen() -> None:
    assert separar_titulo_e_artista("paper plane - the inventors") == (
        "paper plane",
        "the inventors",
    )
    assert separar_titulo_e_artista("Paper Plane \u2013 The Inventors") == (
        "Paper Plane",
        "The Inventors",
    )


def test_by_no_titulo_nao_separa() -> None:
    # "by" aparece em títulos de verdade ("stand by ..."): só o hífen separa o artista.
    assert separar_titulo_e_artista("stand by the door") == ("stand by the door", None)


def test_sem_separador_nao_tem_artista() -> None:
    assert separar_titulo_e_artista("  paper plane ") == ("paper plane", None)


# --- escolher_candidatas ---


def test_candidatas_sem_duplicadas_sem_letra_e_sem_outro_idioma() -> None:
    resultados = [
        _musica(1, "Paper Plane", "The Inventors"),
        _musica(2, "Paper Plane", "Inventors, The"),  # mesma música, outro álbum
        _musica(3, "Paper Plane", "Os Inventores", LETRA_PT),
        _musica(4, "Paper Plane", "Nobody", None),
        _musica(5, "Paper Plane", "Someone Else"),
    ]
    candidatas, fora_do_ingles = escolher_candidatas(resultados, "paper plane")
    assert [(m.id, m.artista) for m in candidatas] == [(1, "The Inventors"), (5, "Someone Else")]
    assert fora_do_ingles is True


def test_titulo_exato_vem_primeiro_e_limita_a_cinco() -> None:
    resultados = [_musica(i, f"Paper Plane Remix {i}", f"Artist {i}") for i in range(10)]
    resultados.append(_musica(99, "Paper plane", "The Inventors"))
    candidatas, _ = escolher_candidatas(resultados, "paper plane")
    assert candidatas[0].id == 99
    assert len(candidatas) == 5


def test_mesmo_artista_e_a_mesma_musica_e_fica_a_de_titulo_exato() -> None:
    # A fonte repete a música em coletâneas, com o título sujo ("[Single, 2017]", "(EP ...)").
    resultados = [
        _musica(1, "Paper Plane [Paper Plane, 2017]", "The Inventors"),
        _musica(2, "Paper Plane -  (EP Paper Plane)", "The Inventors"),
        _musica(3, "Paper Plane", "The Inventors"),
    ]
    candidatas, _ = escolher_candidatas(resultados, "paper plane")
    assert [m.id for m in candidatas] == [3]


def test_sem_resultados() -> None:
    assert escolher_candidatas([], "nada") == ([], False)


# --- filtrar_expressoes ---


def test_so_mantem_expressoes_que_estao_no_verso() -> None:
    verso = "Hold on, the city never sleeps"
    assert filtrar_expressoes(["hold on", "Never Sleeps", "wake up", "hold on"], verso) == [
        "hold on",
        "Never Sleeps",
    ]
