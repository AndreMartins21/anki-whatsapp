"""Prática com letra de música (M13, seção 5.8): funções puras sobre a letra — separar os versos,
checar se está em inglês, escolher as candidatas de uma busca e limpar as expressões que a IA
apontou. Nada aqui faz I/O; a busca da letra fica em `app/services/letras.py` (ADR-0016)."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.domain.choices import normalizar

MAX_VERSOS = 40  # uma música longa vira uma sessão cansativa: pratica só os primeiros
MAX_CANDIDATAS = 5
MIN_PALAVRAS_POR_VERSO = 2
PROPORCAO_MINIMA_DE_INGLES = 0.2

# Palavras muito comuns do inglês que quase não existem em português/espanhol — ficam de fora as
# ambíguas ("a", "no", "me", "so", "de") e as interjeições que toda língua usa ("oh", "yeah").
_TEXTO_DAS_PALAVRAS_DO_INGLES = (
    "i you the and to my your it is in of that on we be for with but this what when all "
    "just don't i'm it's can't won't know love like can will was are have got get now they "
    "she he her his our up out down there if not do at from let go never one time night way "
    "want need feel say see make take come back again been were would could should how why "
    "where who gonna wanna baby tonight heart there's you're i'll i've we're they're ain't"
)
_TEXTO_DAS_INTERJEICOES = "oh ooh ah uh woah whoa yeah yeh hey la na da mmm hmm eh ay ayy yo"
_PALAVRAS_DO_INGLES = frozenset(_TEXTO_DAS_PALAVRAS_DO_INGLES.split())
_INTERJEICOES = frozenset(_TEXTO_DAS_INTERJEICOES.split())
_SO_MARCACAO = re.compile(r"^[\[(].*[\])]$")  # [Chorus], (x2)
_PALAVRA = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)?")
_SEPARADOR_DE_ARTISTA = re.compile("\\s+[-\u2013\u2014]\\s+")  # hífen, meia-risca, travessão


@dataclass(frozen=True)
class Musica:
    """Um registro da fonte de letras. `letra` é `None` quando a fonte não tem o texto."""

    id: int
    titulo: str
    artista: str
    letra: str | None = None


def _palavras(texto: str) -> list[str]:
    return _PALAVRA.findall(texto.lower().replace("\u2019", "'"))  # \u2019 = apóstrofo curvo


def extrair_versos(letra: str) -> list[str]:
    """Linhas com conteúdo, na ordem, sem marcações (`[Chorus]`), sem as que só têm interjeições
    ou uma palavra, e sem repetições (o refrão aparece uma vez só). No máximo `MAX_VERSOS`."""
    versos: list[str] = []
    vistos: set[str] = set()
    for linha in letra.splitlines():
        verso = linha.strip()
        if not verso or _SO_MARCACAO.match(verso):
            continue
        palavras = _palavras(verso)
        if len(palavras) < MIN_PALAVRAS_POR_VERSO or all(p in _INTERJEICOES for p in palavras):
            continue
        chave = normalizar(verso)
        if chave in vistos:
            continue
        vistos.add(chave)
        versos.append(verso)
        if len(versos) == MAX_VERSOS:
            break
    return versos


def eh_ingles(letra: str) -> bool:
    """Heurística sem IA: a proporção de palavras muito comuns do inglês. Numa letra em inglês
    ela passa folgado de 20%; em português, espanhol ou coreano fica perto de zero."""
    palavras = _palavras(letra)
    if not palavras:
        return False
    comuns = sum(1 for p in palavras if p in _PALAVRAS_DO_INGLES)
    return comuns / len(palavras) >= PROPORCAO_MINIMA_DE_INGLES


def separar_titulo_e_artista(texto: str) -> tuple[str, str | None]:
    """`paper plane - the inventors` -> título e artista. Só o hífen separa: "by" aparece em
    títulos de verdade."""
    partes = _SEPARADOR_DE_ARTISTA.split(texto.strip(), maxsplit=1)
    if len(partes) == 2 and partes[0].strip() and partes[1].strip():
        return partes[0].strip(), partes[1].strip()
    return texto.strip(), None


def _artista_normalizado(artista: str) -> str:
    """`Inventors, The` e `The Inventors` são o mesmo artista."""
    nome = normalizar(artista)
    if nome.endswith(" the"):
        nome = nome[: -len(" the")]
    return nome.removeprefix("the ")


def escolher_candidatas(
    resultados: Sequence[Musica], titulo_buscado: str
) -> tuple[list[Musica], bool]:
    """Da busca, as músicas que dá para praticar: com letra, em inglês, uma por artista (a fonte
    repete a mesma música em coletâneas, com o título sujo) e com o título exato primeiro — é a
    versão que fica quando o artista se repete. Devolve também se alguma foi descartada por
    estar em outro idioma, para a mensagem de "não achei" explicar o porquê."""
    alvo = normalizar(titulo_buscado)
    # `sorted` é estável: fora o título exato na frente, mantém a ordem (relevância) da fonte.
    ordenados = sorted(resultados, key=lambda m: normalizar(m.titulo) != alvo)
    candidatas: list[Musica] = []
    artistas: set[str] = set()
    fora_do_ingles = False
    for musica in ordenados:
        if not musica.letra or not musica.letra.strip():
            continue
        if not eh_ingles(musica.letra):
            fora_do_ingles = True
            continue
        artista = _artista_normalizado(musica.artista)
        if artista in artistas:
            continue
        artistas.add(artista)
        candidatas.append(musica)
    return candidatas[:MAX_CANDIDATAS], fora_do_ingles


def filtrar_expressoes(expressoes: Iterable[str], verso: str) -> list[str]:
    """Só as expressões que estão mesmo no verso (a IA às vezes aponta uma palavra de fora), sem
    repetição."""
    no_verso = f" {normalizar(verso)} "
    mantidas: list[str] = []
    vistas: set[str] = set()
    for expressao in expressoes:
        chave = normalizar(expressao)
        if not chave or chave in vistas or f" {chave} " not in no_verso:
            continue
        vistas.add(chave)
        mantidas.append(expressao.strip())
    return mantidas
