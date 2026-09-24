"""Músicas do simulador (M13): letras **inventadas** para o projeto, nunca letra real (ADR-0016).
Duas homônimas em inglês, para exercitar a escolha, e uma em português, para a recusa. Use
`--letras-reais` para buscar no LRCLIB de verdade."""

from __future__ import annotations

from app.domain.musica import Musica
from app.services.letras import FakeLyrics

_PAPER_PLANE = """[Verse 1]
I left my keys beside the kitchen door
The morning bus is running late once more
I wrote your name on a paper plane
And let it drift across the pouring rain

[Chorus]
Hold on, the city never sleeps
Hold on, the city never sleeps
We keep on walking till the sun comes up
"""

_PAPER_PLANE_ACOUSTIC = """Paper plane, where did you land tonight
I kept the window open just in case
Every letter that I never sent
Is folded up and hidden in my case
"""

_AVIAO_DE_PAPEL = """Deixei a chave na porta da cozinha
O ônibus da manhã atrasou de novo
Escrevi seu nome num avião de papel
"""

MUSICAS_DO_SIMULADOR = [
    Musica(1, "Paper Plane", "The Inventors", _PAPER_PLANE),
    Musica(2, "Paper Plane", "Quiet Harbor", _PAPER_PLANE_ACOUSTIC),
    Musica(3, "Aviao de Papel", "Os Inventores", _AVIAO_DE_PAPEL),
]


def letras_do_simulador() -> FakeLyrics:
    return FakeLyrics(list(MUSICAS_DO_SIMULADOR))
