"""Testes de app/services/lembretes.py (M10, ADR-0012): a decisão de um tick, com relógio
controlado e sem `sleep` real — nunca dispara sem chat_id, nunca dois lembretes sem resposta,
nunca sem nada vencido, e adia (sem desistir) enquanto a conversa está aberta."""

from __future__ import annotations

from datetime import timedelta
from zoneinfo import ZoneInfo

from app.domain.models import Entry, Estado, Profile, SentidoSalvo
from app.services.fake_llm import FakeTutor
from app.services.lembretes import Agendador
from tests.helpers import CHAT, T0, Montagem, montar

UTC = ZoneInfo("UTC")
SENTIDO = SentidoSalvo(traducao="travar", definicao="to stop making progress")


def _entrada_vencida(slug: str = "stall") -> Entry:
    return Entry(
        slug=slug,
        palavra=slug,
        classe="verb",
        cefr_estimado="B2",
        sentido=SENTIDO,
        criado_em=T0 - timedelta(days=10),
        atualizado_em=T0 - timedelta(days=10),
    )


def _agendador(m: Montagem) -> Agendador:
    async def dormir(_: float) -> None:
        return None

    return Agendador(router=m.router, repo=m.repo, agora=m.relogio.agora, fuso=UTC, dormir=dormir)


async def test_tick_nao_dispara_com_lembretes_desligados() -> None:
    m = montar()
    m.repo.salvar_perfil(Profile(nivel="B1-B2", chat_id=CHAT, lembretes_por_dia=0))
    agendador = _agendador(m)

    await agendador._tick()

    assert m.channel.textos_enviados == []


async def test_tick_nao_dispara_sem_chat_id() -> None:
    m = montar()
    m.repo.salvar_perfil(Profile(nivel="B1-B2", chat_id=None, lembretes_por_dia=3))
    agendador = _agendador(m)

    await agendador._tick()

    assert m.channel.textos_enviados == []


async def test_tick_agenda_o_proximo_horario_na_primeira_vez_sem_disparar() -> None:
    m = montar()
    m.repo.salvar_perfil(
        Profile(nivel="B1-B2", chat_id=CHAT, lembretes_por_dia=3, janela_inicio=9, janela_fim=21)
    )
    agendador = _agendador(m)

    await agendador._tick()

    assert m.channel.textos_enviados == []
    perfil = m.repo.obter_perfil()
    assert perfil is not None
    assert perfil.proximo_lembrete is not None


async def test_tick_ainda_nao_chegou_a_hora() -> None:
    m = montar()
    m.repo.salvar_perfil(
        Profile(
            nivel="B1-B2",
            chat_id=CHAT,
            lembretes_por_dia=3,
            proximo_lembrete=T0 + timedelta(hours=1),
        )
    )
    agendador = _agendador(m)

    await agendador._tick()

    assert m.channel.textos_enviados == []


async def test_tick_dispara_no_horario_e_marca_backoff() -> None:
    m = montar(tutor=FakeTutor())
    m.repo.criar_entrada(_entrada_vencida())
    m.repo.salvar_perfil(
        Profile(
            nivel="B1-B2",
            chat_id=CHAT,
            lembretes_por_dia=3,
            janela_inicio=9,
            janela_fim=21,
            proximo_lembrete=T0,
        )
    )
    agendador = _agendador(m)

    await agendador._tick()

    assert len(m.channel.textos_enviados) == 1
    assert "Practice time" in m.channel.textos_enviados[0][1]
    perfil = m.repo.obter_perfil()
    assert perfil is not None
    assert perfil.lembrete_sem_resposta is True
    assert perfil.proximo_lembrete is not None
    assert perfil.proximo_lembrete > T0
    assert m.repo.obter_sessao().estado == Estado.REVIEWING


async def test_tick_nao_dispara_de_novo_sem_resposta_ao_anterior() -> None:
    m = montar()
    m.repo.criar_entrada(_entrada_vencida())
    m.repo.salvar_perfil(
        Profile(
            nivel="B1-B2",
            chat_id=CHAT,
            lembretes_por_dia=3,
            proximo_lembrete=T0,
            lembrete_sem_resposta=True,
        )
    )
    agendador = _agendador(m)

    await agendador._tick()

    assert m.channel.textos_enviados == []
    perfil = m.repo.obter_perfil()
    assert perfil is not None
    assert perfil.proximo_lembrete is not None
    assert perfil.proximo_lembrete > T0  # recalculou, para não travar para sempre


async def test_tick_adia_com_sessao_aberta_sem_desistir() -> None:
    m = montar()
    m.repo.criar_entrada(_entrada_vencida())
    m.repo.salvar_perfil(
        Profile(nivel="B1-B2", chat_id=CHAT, lembretes_por_dia=3, proximo_lembrete=T0)
    )
    m.repo.salvar_sessao(m.repo.obter_sessao().model_copy(update={"estado": Estado.AWAIT_ACTION}))
    agendador = _agendador(m)

    await agendador._tick()

    assert m.channel.textos_enviados == []
    perfil = m.repo.obter_perfil()
    assert perfil is not None
    assert perfil.proximo_lembrete == T0  # não desistiu: tenta de novo no próximo tick


async def test_tick_desiste_depois_de_2_horas_de_atraso() -> None:
    m = montar()
    m.repo.criar_entrada(_entrada_vencida())
    m.repo.salvar_perfil(
        Profile(
            nivel="B1-B2",
            chat_id=CHAT,
            lembretes_por_dia=3,
            proximo_lembrete=T0 - timedelta(hours=3),
        )
    )
    agendador = _agendador(m)

    await agendador._tick()

    assert m.channel.textos_enviados == []
    perfil = m.repo.obter_perfil()
    assert perfil is not None
    assert perfil.proximo_lembrete is not None
    assert perfil.proximo_lembrete > T0  # desistiu do horário atrasado e recalculou


async def test_tick_sem_nada_vencido_nao_dispara_nem_marca_backoff() -> None:
    m = montar()
    # Nenhuma entrada: não há nada a revisar.
    m.repo.salvar_perfil(
        Profile(nivel="B1-B2", chat_id=CHAT, lembretes_por_dia=3, proximo_lembrete=T0)
    )
    agendador = _agendador(m)

    await agendador._tick()

    assert m.channel.textos_enviados == []
    perfil = m.repo.obter_perfil()
    assert perfil is not None
    assert perfil.lembrete_sem_resposta is False
    assert perfil.proximo_lembrete is not None
    assert perfil.proximo_lembrete > T0
