"""M15 (ADR-0018): o bot não fica em grupo que nenhum admin ativou. O agendador sai dos pendentes
há mais de 24 h, em silêncio, com o relógio controlado."""

from __future__ import annotations

from datetime import timedelta
from zoneinfo import ZoneInfo

from app.services.lembretes import DESISTIR_DE_SAIR_APOS, Agendador
from tests.helpers import T0, Montagem, montar

GRUPO = "120363000000000001@g.us"
OUTRO = "120363000000000002@g.us"


def _agendador(m: Montagem, *, sair=None) -> Agendador:  # type: ignore[no-untyped-def]
    async def dormir(_: float) -> None:
        return None

    return Agendador(
        router=m.router,
        banco=m.banco,
        agora=m.relogio.agora,
        fuso=ZoneInfo("UTC"),
        dormir=dormir,
        sair_do_grupo=sair or m.channel.leave_group,
    )


async def test_sai_do_grupo_pendente_depois_de_24_horas_e_apaga_o_registro() -> None:
    m = montar()
    m.banco.registrar_grupo_pendente(GRUPO, T0 - timedelta(hours=25))

    await _agendador(m)._tick()

    assert m.channel.grupos_deixados == [GRUPO]
    assert m.banco.listar_grupos_pendentes() == []
    assert m.channel.textos_enviados == []  # sai sem dizer nada


async def test_antes_de_24_horas_o_bot_continua_no_grupo() -> None:
    m = montar()
    m.banco.registrar_grupo_pendente(GRUPO, T0 - timedelta(hours=23, minutes=59))

    await _agendador(m)._tick()

    assert m.channel.grupos_deixados == []
    assert len(m.banco.listar_grupos_pendentes()) == 1


async def test_o_prazo_conta_a_partir_do_primeiro_encontro_com_o_grupo() -> None:
    m = montar()
    m.banco.registrar_grupo_pendente(GRUPO, T0)
    m.banco.registrar_grupo_pendente(
        GRUPO, T0 + timedelta(hours=20)
    )  # mensagens depois: não reinicia
    m.relogio.avancar(timedelta(hours=24, minutes=1))

    await _agendador(m)._tick()

    assert m.channel.grupos_deixados == [GRUPO]


async def test_grupo_ativado_antes_do_prazo_nao_e_deixado() -> None:
    m = montar()
    m.banco.registrar_grupo_pendente(GRUPO, T0 - timedelta(hours=20))
    m.banco.ativar_grupo(GRUPO, nome=None, por="5531999998888", agora=T0)
    m.relogio.avancar(timedelta(hours=10))

    await _agendador(m)._tick()

    assert m.channel.grupos_deixados == []
    assert m.banco.grupo_esta_ativo(GRUPO)


async def test_sai_so_dos_vencidos_e_os_outros_seguem_pendentes() -> None:
    m = montar()
    m.banco.registrar_grupo_pendente(GRUPO, T0 - timedelta(hours=30))
    m.banco.registrar_grupo_pendente(OUTRO, T0 - timedelta(hours=1))

    await _agendador(m)._tick()

    assert m.channel.grupos_deixados == [GRUPO]
    assert [g for g, _ in m.banco.listar_grupos_pendentes()] == [OUTRO]


async def test_falha_ao_sair_mantem_o_registro_para_tentar_no_proximo_tick() -> None:
    m = montar()
    m.banco.registrar_grupo_pendente(GRUPO, T0 - timedelta(hours=25))

    async def quebra(_: str) -> None:
        raise RuntimeError("WAHA fora do ar")

    await _agendador(m, sair=quebra)._tick()

    assert len(m.banco.listar_grupos_pendentes()) == 1  # ainda lá
    await _agendador(m)._tick()  # o WAHA voltou
    assert m.channel.grupos_deixados == [GRUPO]
    assert m.banco.listar_grupos_pendentes() == []


async def test_uma_falha_nao_impede_a_saida_dos_outros_grupos() -> None:
    m = montar()
    m.banco.registrar_grupo_pendente(GRUPO, T0 - timedelta(hours=26))
    m.banco.registrar_grupo_pendente(OUTRO, T0 - timedelta(hours=25))

    async def quebra_no_primeiro(grupo: str) -> None:
        if grupo == GRUPO:
            raise RuntimeError("falha só neste grupo")
        await m.channel.leave_group(grupo)

    await _agendador(m, sair=quebra_no_primeiro)._tick()

    assert m.channel.grupos_deixados == [OUTRO]


async def test_depois_de_muito_tempo_falhando_desiste_e_apaga_o_registro() -> None:
    """Se o bot já foi removido do grupo, `leave` falha para sempre: não tentar todo minuto."""
    m = montar()
    m.banco.registrar_grupo_pendente(GRUPO, T0 - DESISTIR_DE_SAIR_APOS - timedelta(minutes=1))

    async def quebra(_: str) -> None:
        raise RuntimeError("o bot nem está mais no grupo")

    await _agendador(m, sair=quebra)._tick()

    assert m.banco.listar_grupos_pendentes() == []


async def test_sem_funcao_de_sair_o_agendador_nao_mexe_nos_grupos() -> None:
    m = montar()
    m.banco.registrar_grupo_pendente(GRUPO, T0 - timedelta(hours=50))
    agendador = Agendador(
        router=m.router, banco=m.banco, agora=m.relogio.agora, fuso=ZoneInfo("UTC")
    )

    await agendador._tick()

    assert len(m.banco.listar_grupos_pendentes()) == 1
