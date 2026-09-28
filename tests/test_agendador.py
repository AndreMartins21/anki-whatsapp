"""Testes de app/services/lembretes.py (M10, ADR-0012): a decisão de um tick, com relógio
controlado e sem `sleep` real — nunca dispara sem chat_id, nunca dois lembretes sem resposta,
nunca sem nada vencido, e adia (sem desistir) enquanto a conversa está aberta."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.domain.models import Entry, Estado, Profile, SentidoSalvo
from app.services.fake_llm import FakeTutor
from app.services.lembretes import Agendador
from app.services.metricas_destino import DestinoEmMemoria
from tests.helpers import CHAT, T0, Montagem, eventos, montar

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

    return Agendador(router=m.router, banco=m.banco, agora=m.relogio.agora, fuso=UTC, dormir=dormir)


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


# --- eventos estruturados (M27, ADR-0028, seção 12 da spec) ------------------------------------


async def test_lembrete_enviado_registra_evento_com_o_tamanho_da_fila(
    caplog: pytest.LogCaptureFixture,
) -> None:
    m = montar(tutor=FakeTutor())
    m.repo.criar_entrada(_entrada_vencida())
    m.repo.salvar_perfil(
        Profile(nivel="B1-B2", chat_id=CHAT, lembretes_por_dia=3, proximo_lembrete=T0)
    )
    with caplog.at_level(logging.INFO):
        await _agendador(m)._tick()

    (evento,) = eventos(caplog.records, "lembrete_enviado")
    assert evento.tipo_espaco == "privado"
    assert evento.n == 1


async def test_lembrete_desistido_por_sem_resposta_anterior(
    caplog: pytest.LogCaptureFixture,
) -> None:
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
    with caplog.at_level(logging.INFO):
        await _agendador(m)._tick()

    (evento,) = eventos(caplog.records, "lembrete_desistido")
    assert evento.motivo == "sem_resposta_anterior"


async def test_lembrete_desistido_por_atraso(caplog: pytest.LogCaptureFixture) -> None:
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
    with caplog.at_level(logging.INFO):
        await _agendador(m)._tick()

    (evento,) = eventos(caplog.records, "lembrete_desistido")
    assert evento.motivo == "atraso"


async def test_lembrete_adiado_por_sessao_aberta(caplog: pytest.LogCaptureFixture) -> None:
    m = montar()
    m.repo.criar_entrada(_entrada_vencida())
    m.repo.salvar_perfil(
        Profile(nivel="B1-B2", chat_id=CHAT, lembretes_por_dia=3, proximo_lembrete=T0)
    )
    m.repo.salvar_sessao(m.repo.obter_sessao().model_copy(update={"estado": Estado.AWAIT_ACTION}))

    with caplog.at_level(logging.INFO):
        await _agendador(m)._tick()

    (evento,) = eventos(caplog.records, "lembrete_adiado")
    assert evento.motivo == "conversa_em_andamento"


async def test_lembrete_adiado_por_nada_vencido(caplog: pytest.LogCaptureFixture) -> None:
    m = montar()
    m.repo.salvar_perfil(
        Profile(nivel="B1-B2", chat_id=CHAT, lembretes_por_dia=3, proximo_lembrete=T0)
    )

    with caplog.at_level(logging.INFO):
        await _agendador(m)._tick()

    (evento,) = eventos(caplog.records, "lembrete_adiado")
    assert evento.motivo == "nada_vencido"


# --- snapshot diário de métricas (M28, ADR-0029, seção 12 da spec) -----------------------------


def _agendador_com_destino(
    m: Montagem, *, destino: DestinoEmMemoria | None, hora: int = 4
) -> Agendador:
    async def dormir(_: float) -> None:
        return None

    return Agendador(
        router=m.router,
        banco=m.banco,
        agora=m.relogio.agora,
        fuso=UTC,
        dormir=dormir,
        destino_de_metricas=destino,
        hora_do_snapshot=hora,
    )


async def test_snapshot_desligado_sem_destino_configurado() -> None:
    m = montar()
    m.relogio.agora_ = datetime(2026, 9, 20, 4, 0, tzinfo=UTC)
    agendador = _agendador_com_destino(m, destino=None)

    await agendador._tick()

    assert m.banco.obter_ultimo_snapshot() is None


async def test_snapshot_fora_da_hora_nao_roda(caplog: pytest.LogCaptureFixture) -> None:
    m = montar()
    m.relogio.agora_ = datetime(2026, 9, 20, 5, 0, tzinfo=UTC)
    destino = DestinoEmMemoria()
    agendador = _agendador_com_destino(m, destino=destino)

    with caplog.at_level(logging.INFO):
        await agendador._tick()

    assert m.banco.obter_ultimo_snapshot() is None
    assert destino.gravados == {}
    assert eventos(caplog.records, "snapshot_ok") == []


async def test_snapshot_roda_na_hora_e_grava_todas_as_tabelas(
    caplog: pytest.LogCaptureFixture,
) -> None:
    m = montar()
    m.relogio.agora_ = datetime(2026, 9, 20, 4, 0, tzinfo=UTC)
    m.repo.salvar_perfil(Profile(nivel="B1-B2", criado_em=m.relogio.agora_))
    destino = DestinoEmMemoria()
    agendador = _agendador_com_destino(m, destino=destino)

    with caplog.at_level(logging.INFO):
        await agendador._tick()

    assert m.banco.obter_ultimo_snapshot() == date(2026, 9, 20)
    assert set(destino.gravados) == {
        ("espacos", date(2026, 9, 20)),
        ("pessoas", date(2026, 9, 20)),
        ("admins", date(2026, 9, 20)),
        ("termos", date(2026, 9, 20)),
        ("grupos_pendentes", date(2026, 9, 20)),
        ("firestore_uso", date(2026, 9, 20)),
    }
    assert destino.gravados[("espacos", date(2026, 9, 20))] != b""
    (evento,) = eventos(caplog.records, "snapshot_ok")
    assert evento.n >= 1


async def test_snapshot_nao_roda_duas_vezes_no_mesmo_dia() -> None:
    m = montar()
    m.relogio.agora_ = datetime(2026, 9, 20, 4, 0, tzinfo=UTC)
    destino = DestinoEmMemoria()
    agendador = _agendador_com_destino(m, destino=destino)
    await agendador._tick()
    destino.gravados.clear()

    m.relogio.avancar(timedelta(minutes=1))
    await agendador._tick()

    assert destino.gravados == {}  # não gravou de novo


async def test_snapshot_do_dia_seguinte_roda_de_novo() -> None:
    m = montar()
    m.relogio.agora_ = datetime(2026, 9, 20, 4, 0, tzinfo=UTC)
    destino = DestinoEmMemoria()
    agendador = _agendador_com_destino(m, destino=destino)
    await agendador._tick()

    m.relogio.agora_ = datetime(2026, 9, 21, 4, 0, tzinfo=UTC)
    await agendador._tick()

    assert m.banco.obter_ultimo_snapshot() == date(2026, 9, 21)


async def test_snapshot_com_falha_registra_evento_e_nao_marca(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class _DestinoQueFalha:
        def gravar(self, tabela: str, dia: date, linhas: list[object]) -> None:
            raise RuntimeError("GCS fora do ar")

    m = montar()
    m.relogio.agora_ = datetime(2026, 9, 20, 4, 0, tzinfo=UTC)
    agendador = _agendador_com_destino(m, destino=_DestinoQueFalha())  # type: ignore[arg-type]

    with caplog.at_level(logging.INFO):
        await agendador._tick()  # não pode levantar: o tick engole a falha (como os demais passos)

    assert m.banco.obter_ultimo_snapshot() is None
    assert eventos(caplog.records, "snapshot_falhou") != []
    assert eventos(caplog.records, "snapshot_ok") == []
