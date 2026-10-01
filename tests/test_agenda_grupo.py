"""M35 (ADR-0033): agenda da revisão diária do grupo — funções puras e o agendador."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.domain.agenda_grupo import parse_diaria, parse_horario, proxima_diaria
from app.domain.models import Membro, Profile
from app.services.lembretes import Agendador
from tests.helpers import ANA, GRUPO, Montagem, montar
from tests.test_agendador import _entrada_vencida

SP = ZoneInfo("America/Sao_Paulo")


def _local(dia: int, hora: int, minuto: int = 0) -> datetime:
    return datetime(2026, 9, dia, hora, minuto, tzinfo=SP)  # 21/09/2026 é segunda-feira


# --- puro -------------------------------------------------------------------------------------


def test_proxima_diaria_hoje_se_ainda_nao_passou() -> None:
    assert proxima_diaria(_local(21, 10), 19, 0, False) == _local(21, 19)


def test_proxima_diaria_amanha_se_ja_passou() -> None:
    assert proxima_diaria(_local(21, 19, 30), 19, 0, False) == _local(22, 19)


def test_sexta_a_noite_pula_o_fim_de_semana_ate_segunda() -> None:
    sexta = _local(25, 20)

    assert proxima_diaria(sexta, 19, 0, False) == _local(28, 19)
    assert proxima_diaria(sexta, 19, 0, True) == _local(26, 19)


def test_sabado_de_manha_com_fim_de_semana_ligado_toca_no_mesmo_dia() -> None:
    assert proxima_diaria(_local(26, 8), 19, 0, True) == _local(26, 19)
    assert proxima_diaria(_local(26, 8), 19, 0, False) == _local(28, 19)


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [("19h", (19, 0)), ("19:30", (19, 30)), ("7", (7, 0)), ("19h30", (19, 30))],
)
def test_parse_horario(texto: str, esperado: tuple[int, int]) -> None:
    assert parse_horario(texto) == esperado


@pytest.mark.parametrize("texto", ["25h", "19:61", "abc", ""])
def test_parse_horario_invalido(texto: str) -> None:
    assert parse_horario(texto) is None


def test_parse_diaria_combinado() -> None:
    assert parse_diaria("20h weekends on size 4") == {
        "diaria_hora": 20,
        "diaria_minuto": 0,
        "diaria_ligada": True,
        "diaria_fim_de_semana": True,
        "tamanho_revisao": 4,
    }
    assert parse_diaria("off") == {"diaria_ligada": False}
    assert parse_diaria("size auto") == {"tamanho_revisao": None}


@pytest.mark.parametrize("texto", ["", "weekends", "weekends maybe", "size 0", "size 21", "banana"])
def test_parse_diaria_invalido(texto: str) -> None:
    assert parse_diaria(texto) is None


# --- agendador --------------------------------------------------------------------------------


def _agendador(m: Montagem) -> Agendador:
    async def dormir(_: float) -> None:
        return None

    return Agendador(router=m.router, banco=m.banco, agora=m.relogio.agora, fuso=SP, dormir=dormir)


def _grupo(m: Montagem, agora: datetime, **perfil: object) -> None:
    m.relogio.agora_ = agora.astimezone(UTC)
    repo = m.banco.do_espaco(GRUPO)
    repo.salvar_membro(ANA.numero, Membro(nome="Ana", entrou_em=m.relogio.agora_))
    repo.criar_entrada(_entrada_vencida())
    repo.salvar_perfil(Profile(nivel="B1-B2", chat_id=GRUPO, **perfil))


async def test_o_primeiro_tick_calcula_a_proxima_diaria_sem_mandar_nada() -> None:
    m = montar()
    _grupo(m, _local(21, 10))  # segunda, 10h

    await _agendador(m)._tick()

    perfil = m.banco.do_espaco(GRUPO).obter_perfil()
    assert perfil is not None and perfil.proxima_diaria == _local(21, 19).astimezone(UTC)
    assert m.channel.textos_enviados == []


async def test_dispara_as_19h_de_um_dia_util_e_agenda_o_proximo() -> None:
    m = montar()
    _grupo(m, _local(21, 19, 1), proxima_diaria=_local(21, 19).astimezone(UTC))

    await _agendador(m)._tick()

    assert "Practice time" in m.channel.textos_enviados[-1][1]
    perfil = m.banco.do_espaco(GRUPO).obter_perfil()
    assert perfil is not None
    assert perfil.proxima_diaria == _local(22, 19).astimezone(UTC)
    assert perfil.revisoes_sem_resposta == 1


async def test_sexta_a_noite_agenda_segunda_e_com_fim_de_semana_agenda_sabado() -> None:
    m = montar()
    _grupo(m, _local(25, 19, 1), proxima_diaria=_local(25, 19).astimezone(UTC))
    await _agendador(m)._tick()
    perfil = m.banco.do_espaco(GRUPO).obter_perfil()
    assert perfil is not None and perfil.proxima_diaria == _local(28, 19).astimezone(UTC)

    m2 = montar()
    _grupo(
        m2,
        _local(25, 19, 1),
        proxima_diaria=_local(25, 19).astimezone(UTC),
        diaria_fim_de_semana=True,
    )
    await _agendador(m2)._tick()
    perfil2 = m2.banco.do_espaco(GRUPO).obter_perfil()
    assert perfil2 is not None and perfil2.proxima_diaria == _local(26, 19).astimezone(UTC)


async def test_atraso_de_mais_de_2h_desiste_do_horario_sem_mandar() -> None:
    m = montar()
    _grupo(m, _local(21, 22), proxima_diaria=_local(21, 19).astimezone(UTC))

    await _agendador(m)._tick()

    assert m.channel.textos_enviados == []
    perfil = m.banco.do_espaco(GRUPO).obter_perfil()
    assert perfil is not None and perfil.proxima_diaria == _local(22, 19).astimezone(UTC)


async def test_diaria_desligada_nao_dispara() -> None:
    m = montar()
    _grupo(m, _local(21, 19, 1), proxima_diaria=_local(21, 19).astimezone(UTC), diaria_ligada=False)

    await _agendador(m)._tick()

    assert m.channel.textos_enviados == []


async def test_pausa_depois_de_tres_sem_resposta_e_volta_na_proxima_mensagem() -> None:
    m = montar()
    _grupo(
        m,
        _local(21, 19, 1),
        proxima_diaria=_local(21, 19).astimezone(UTC),
        revisoes_sem_resposta=3,
    )

    await _agendador(m)._tick()

    assert m.channel.textos_enviados == []  # pausada
    await m.diz_no_grupo(ANA, "!daily")  # alguém fala: zera o contador
    perfil = m.banco.do_espaco(GRUPO).obter_perfil()
    assert perfil is not None and perfil.revisoes_sem_resposta == 0


async def test_sessao_ocupada_adia_e_sessao_expirada_nao_bloqueia() -> None:
    from app.domain.models import Estado, Sessao

    m = montar()
    _grupo(m, _local(21, 19, 1), proxima_diaria=_local(21, 19).astimezone(UTC))
    repo = m.banco.do_espaco(GRUPO)
    repo.salvar_sessao(
        Sessao(estado=Estado.AWAIT_ACTION, entry_id="stall", atualizado_em=m.relogio.agora_)
    )
    await _agendador(m)._tick()
    assert m.channel.textos_enviados == []  # conversa em andamento: adia

    repo.salvar_sessao(
        Sessao(
            estado=Estado.AWAIT_ACTION,
            entry_id="stall",
            atualizado_em=m.relogio.agora_ - timedelta(hours=4),
        )
    )
    await _agendador(m)._tick()
    assert "Practice time" in m.channel.textos_enviados[-1][1]  # abandonada há 4h: não bloqueia


async def test_sem_palavras_fica_em_silencio_e_agenda_o_proximo() -> None:
    m = montar()
    _grupo(m, _local(21, 19, 1), proxima_diaria=_local(21, 19).astimezone(UTC))
    m.banco.do_espaco(GRUPO).apagar_entrada("stall")

    await _agendador(m)._tick()

    assert m.channel.textos_enviados == []
    perfil = m.banco.do_espaco(GRUPO).obter_perfil()
    assert perfil is not None and perfil.proxima_diaria == _local(22, 19).astimezone(UTC)
