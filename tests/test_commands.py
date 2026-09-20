"""Testes dos comandos (seção 5.2)."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.models import Estado
from app.services.fake_llm import FakeTutor
from tests.helpers import Montagem, avaliacao, expansoes, explicacao_stall, montar


async def _com_stall_praticada() -> Montagem:
    m = montar(
        tutor=FakeTutor(
            explicacoes=[explicacao_stall()], avaliacoes=[avaliacao()], expansoes=[expansoes()]
        )
    )
    await m.diz("stall | the talks stalled")
    await m.diz("the project stalled")
    await m.diz("3")  # concluir -> oferece expansões
    await m.diz("1,2")
    await m.diz("2")  # depois
    return m


async def test_ajuda_lista_os_comandos() -> None:
    m = montar()

    (resposta,) = await m.diz("/ajuda")

    for comando in (
        "/lista",
        "/pendentes",
        "/praticar",
        "/exportar",
        "/apagar",
        "/nivel",
        "/cancelar",
        "/status",
    ):
        assert comando in resposta


async def test_comando_ignora_maiusculas_e_espacos() -> None:
    m = montar()

    (resposta,) = await m.diz("  /AJUDA ")

    assert "Comandos" in resposta


async def test_comando_desconhecido() -> None:
    m = montar()

    (resposta,) = await m.diz("/voar")

    assert "Não conheço esse comando" in resposta


async def test_lista_sem_palavras() -> None:
    m = montar()

    (resposta,) = await m.diz("/lista")

    assert "ainda não tem palavras" in resposta


async def test_lista_mostra_praticadas_e_novas() -> None:
    m = await _com_stall_praticada()

    (resposta,) = await m.diz("/lista")

    assert resposta.startswith("📚 *Suas palavras* (3)")
    assert "✅ stall — travar, emperrar" in resposta
    assert "🆕 stall for time — enrolar" in resposta


async def test_pendentes_so_as_novas() -> None:
    m = await _com_stall_praticada()

    (resposta,) = await m.diz("/pendentes")

    assert "*Pendentes* (2)" in resposta
    assert "stall for time" in resposta
    assert "• stall —" not in resposta


async def test_pendentes_vazio() -> None:
    m = montar()

    (resposta,) = await m.diz("/pendentes")

    assert "Nenhuma palavra pendente" in resposta


async def test_praticar_sem_argumento_pega_a_pendente_mais_antiga() -> None:
    expl = explicacao_stall().model_copy(
        update={"palavra": "stall for time", "sentido_do_contexto": "s1"}
    )
    m = await _com_stall_praticada()
    m.tutor.explicacoes.append(expl)

    (resposta,) = await m.diz("/praticar")

    assert resposta.startswith("*STALL FOR TIME*")
    assert m.tutor.chamadas[-1] == ("explain", ("stall for time", "B1-B2"))
    assert m.repo.obter_sessao().entry_id == "stall-for-time"


async def test_praticar_com_palavra_acha_pelo_slug_ou_pela_palavra() -> None:
    expl = explicacao_stall()
    m = await _com_stall_praticada()
    m.tutor.explicacoes.extend([expl, expl])

    await m.diz("/praticar stall")
    await m.diz("/praticar Stall")

    assert [c[1][0] for c in m.tutor.chamadas if c[0] == "explain"][-2:] == ["stall", "stall"]


async def test_praticar_palavra_que_nao_existe() -> None:
    m = montar()

    (resposta,) = await m.diz("/praticar hedge")

    assert 'Não achei "hedge"' in resposta


async def test_praticar_sem_pendentes() -> None:
    m = montar()

    (resposta,) = await m.diz("/praticar")

    assert "Nenhuma palavra pendente" in resposta


async def test_apagar_remove_a_entrada_e_as_frases() -> None:
    m = await _com_stall_praticada()

    (resposta,) = await m.diz("/apagar stall")

    assert "🗑️ *stall* apagada." in resposta
    assert m.repo.obter_entrada("stall") is None
    assert m.repo.listar_frases("stall") == []
    assert len(m.repo.listar_entradas()) == 2


async def test_apagar_a_palavra_em_andamento_zera_a_sessao() -> None:
    m = montar(tutor=FakeTutor(explicacoes=[explicacao_stall()]))
    await m.diz("stall")

    await m.diz("/apagar stall")

    sessao = m.repo.obter_sessao()
    assert sessao.estado == Estado.IDLE
    assert sessao.entry_id is None


async def test_apagar_sem_argumento_ou_inexistente() -> None:
    m = montar()

    (sem_argumento,) = await m.diz("/apagar")
    (inexistente,) = await m.diz("/apagar hedge")

    assert "Não conheço" in sem_argumento
    assert 'Não achei "hedge"' in inexistente


async def test_nivel_mostra_e_altera() -> None:
    m = montar()

    (atual,) = await m.diz("/nivel")
    (alterado,) = await m.diz("/nivel b2-c1")
    (depois,) = await m.diz("/nivel")

    assert "*B1-B2*" in atual
    assert "ajustado para *B2-C1*" in alterado
    assert "*B2-C1*" in depois
    perfil = m.repo.obter_perfil()
    assert perfil is not None
    assert perfil.nivel == "B2-C1"


async def test_nivel_invalido_nao_muda() -> None:
    m = montar()

    (resposta,) = await m.diz("/nivel C2")

    assert "Nível inválido" in resposta
    perfil = m.repo.obter_perfil()
    assert perfil is not None
    assert perfil.nivel == "B1-B2"


async def test_cancelar_volta_para_idle_sem_apagar_nada() -> None:
    m = montar(tutor=FakeTutor(explicacoes=[explicacao_stall()]))
    await m.diz("stall")

    (resposta,) = await m.diz("/cancelar")

    assert "continua salvo" in resposta
    assert m.repo.obter_sessao().estado == Estado.IDLE
    assert m.repo.obter_entrada("stall") is not None


async def test_comando_no_meio_do_fluxo_nao_desmonta_a_sessao() -> None:
    m = montar(tutor=FakeTutor(explicacoes=[explicacao_stall()]))
    await m.diz("stall")

    await m.diz("/ajuda")

    assert m.repo.obter_sessao().estado == Estado.AWAIT_CHOICE


async def test_status_mostra_waha_e_contagens() -> None:
    async def status() -> str:
        return "WORKING"

    m = await _com_stall_praticada()
    m.router._status_da_sessao = status

    (resposta,) = await m.diz("/status")

    assert "WAHA): WORKING" in resposta
    assert "Palavras: 3" in resposta
    assert "Pendentes: 2" in resposta


async def test_status_funciona_mesmo_com_o_waha_fora() -> None:
    async def status() -> str:
        raise ConnectionError("fora")

    m = montar(status_da_sessao=status)

    (resposta,) = await m.diz("/status")

    assert "WAHA): indisponível" in resposta


@dataclass
class ExportadorFalso:
    resultado: tuple[str, int] | None
    chamadas: list[bool] = field(default_factory=list)

    def exportar(self, *, tudo: bool) -> tuple[str, int] | None:
        self.chamadas.append(tudo)
        return self.resultado


async def test_exportar_devolve_o_link() -> None:
    exportador = ExportadorFalso(("https://exemplo.test/anki.txt", 4))
    m = montar(exportador=exportador)

    (resposta,) = await m.diz("/exportar")

    assert "4 cartões" in resposta
    assert "https://exemplo.test/anki.txt" in resposta
    assert exportador.chamadas == [False]


async def test_exportar_tudo_pede_tudo() -> None:
    exportador = ExportadorFalso(("https://exemplo.test/anki.txt", 9))
    m = montar(exportador=exportador)

    await m.diz("/exportar tudo")

    assert exportador.chamadas == [True]


async def test_exportar_sem_nada_novo() -> None:
    m = montar(exportador=ExportadorFalso(None))

    (resposta,) = await m.diz("/exportar")

    assert "nada novo para exportar" in resposta


async def test_exportar_sem_exportador_configurado() -> None:
    m = montar()

    (resposta,) = await m.diz("/exportar")

    assert "ainda não está disponível" in resposta
