"""M17: o rodízio da marcação é uma função pura — quem foi marcado há mais tempo (ou nunca) vem
primeiro, com desempate aleatório, sem repetir seguido se houver outro aluno."""

from __future__ import annotations

import random
from collections.abc import Sequence
from datetime import datetime, timedelta

from app.domain.rodizio import Candidato, escolher
from tests.helpers import T0


def _c(numero: str, minutos: int | None = None) -> Candidato:
    return Candidato(numero, None if minutos is None else T0 + timedelta(minutes=minutos))


def _primeiro(itens: Sequence[Candidato]) -> Candidato:
    return itens[0]


def test_sem_candidatos_nao_ha_quem_marcar() -> None:
    assert escolher([]) is None


def test_quem_nunca_foi_marcado_vem_antes_de_quem_ja_foi() -> None:
    assert escolher([_c("a", 5), _c("b"), _c("c", 1)], sortear=_primeiro) == "b"


def test_entre_os_ja_marcados_vem_o_marcado_ha_mais_tempo() -> None:
    assert escolher([_c("a", 30), _c("b", 10), _c("c", 20)], sortear=_primeiro) == "b"


def test_ninguem_e_marcado_duas_vezes_seguidas_se_houver_outro_aluno() -> None:
    candidatos = [_c("a", 1), _c("b", 50)]

    assert escolher(candidatos, excluir="a", sortear=_primeiro) == "b"  # `a` seria o mais antigo


def test_com_um_aluno_so_ele_pode_ser_marcado_de_novo() -> None:
    assert escolher([_c("a", 1)], excluir="a") == "a"


def test_o_desempate_e_aleatorio_so_entre_os_empatados() -> None:
    escolhidos: set[str | None] = set()
    for semente in range(40):
        sorteio = random.Random(semente)  # noqa: S311
        candidatos = [_c("a"), _c("b"), _c("c", 5)]
        escolhidos.add(escolher(candidatos, sortear=sorteio.choice))

    assert escolhidos == {"a", "b"}  # nunca o `c`, que já foi marcado


def test_o_desempate_usa_o_sorteador_recebido() -> None:
    assert escolher([_c("a"), _c("b"), _c("c")], sortear=lambda itens: itens[-1]) == "c"


def test_distribuicao_justa_cada_aluno_e_marcado_o_mesmo_numero_de_vezes() -> None:
    marcado_em: dict[str, datetime | None] = {"a": None, "b": None, "c": None}
    sorteio = random.Random(7)  # noqa: S311
    vezes = {"a": 0, "b": 0, "c": 0}
    anterior: str | None = None

    for passo in range(30):
        candidatos = [Candidato(n, t) for n, t in marcado_em.items()]
        quem = escolher(candidatos, excluir=anterior, sortear=sorteio.choice)
        assert quem is not None and quem != anterior  # nunca duas seguidas
        vezes[quem] += 1
        marcado_em[quem] = T0 + timedelta(minutes=passo)
        anterior = quem

    assert vezes == {"a": 10, "b": 10, "c": 10}


def test_a_ordem_dos_candidatos_nao_muda_o_resultado() -> None:
    a = [_c("a", 3), _c("b", 1), _c("c", 2)]

    assert escolher(a, sortear=_primeiro) == escolher(list(reversed(a)), sortear=_primeiro) == "b"
