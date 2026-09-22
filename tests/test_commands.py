"""Testes dos comandos (seção 5.2, M9: nomes em inglês + apelido em PT-BR)."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.models import Estado, Explanation, Roteamento, Sense
from app.services.anki import ResultadoExportacao
from app.services.fake_llm import FakeTutor
from tests.helpers import Montagem, avaliacao, expansoes, explicacao_stall, montar

HEDGE = Explanation(
    ok=True,
    palavra="hedge",
    classe="verb",
    cefr_estimado="B1",
    sentidos=[
        Sense(
            id="s1",
            traducao="proteger-se",
            definicao="to protect against loss",
            exemplo="[[Hedge]] your bets.",
        )
    ],
    sentido_do_contexto="s1",
    nota="",
    tags=[],
)


def _roteamento_frase(veredito: str = "quase") -> Roteamento:
    av = avaliacao(veredito)
    return Roteamento(
        intencao="frase",
        usa_palavra_alvo=av.usa_palavra_alvo,
        sentido_correto=av.sentido_correto,
        veredito=av.veredito,
        correcoes=av.correcoes,
        versao_natural=av.versao_natural,
        explicacao=av.explicacao,
    )


async def _stall_praticada() -> Montagem:
    m = montar(
        tutor=FakeTutor(
            explicacoes=[explicacao_stall()],
            roteamentos=[_roteamento_frase()],
            expansoes=[expansoes()],
        )
    )
    await m.diz("stall | the talks stalled")
    await m.diz("the project stalled")
    await m.diz("3")  # salva, praticada
    return m


async def _stall_e_hedge() -> Montagem:
    m = await _stall_praticada()
    m.tutor.explicacoes.append(HEDGE)
    m.tutor.expansoes.append(expansoes())
    await m.diz("hedge")
    await m.diz("3")  # salva, nova (não praticada)
    return m


async def test_ajuda_lista_os_comandos() -> None:
    m = montar()

    (resposta,) = await m.diz("/help")

    for comando in (
        "/list",
        "/pending",
        "/practice",
        "/export",
        "/delete",
        "/level",
        "/cancel",
        "/status",
    ):
        assert comando in resposta


async def test_apelido_em_pt_br_continua_funcionando() -> None:
    m = montar()

    (resposta,) = await m.diz("/ajuda")

    assert "Commands" in resposta


async def test_comando_ignora_maiusculas_e_espacos() -> None:
    m = montar()

    (resposta,) = await m.diz("  /HELP ")

    assert "Commands" in resposta


async def test_comando_desconhecido() -> None:
    m = montar()

    (resposta,) = await m.diz("/fly")

    assert "I don't know that command" in resposta


async def test_lista_sem_palavras() -> None:
    m = montar()

    (resposta,) = await m.diz("/list")

    assert "don't have any saved words" in resposta


async def test_lista_mostra_praticadas_e_novas() -> None:
    m = await _stall_e_hedge()

    (resposta,) = await m.diz("/list")

    assert resposta.startswith("📚 *Your words* (2)")
    assert "✅ stall — travar, emperrar" in resposta
    assert "🆕 hedge — proteger-se" in resposta


async def test_pendentes_so_as_novas() -> None:
    m = await _stall_e_hedge()

    (resposta,) = await m.diz("/pending")

    assert "*Pending* (1)" in resposta
    assert "hedge" in resposta
    assert "• stall —" not in resposta


async def test_pendentes_vazio() -> None:
    m = montar()

    (resposta,) = await m.diz("/pending")

    assert "No pending words" in resposta


async def test_praticar_sem_argumento_pega_a_pendente_mais_antiga() -> None:
    m = await _stall_e_hedge()
    m.tutor.explicacoes.append(HEDGE)

    (resposta,) = await m.diz("/practice")

    assert resposta.startswith("*hedge*")
    assert m.tutor.chamadas[-1] == ("explain", ("hedge", "B1-B2"))
    assert m.repo.obter_sessao().entry_id == "hedge"


async def test_praticar_com_palavra_acha_pelo_slug_ou_pela_palavra() -> None:
    m = await _stall_e_hedge()
    m.tutor.explicacoes.extend([explicacao_stall(), explicacao_stall()])

    await m.diz("/praticar stall")
    await m.diz("/practice Stall")

    assert [c[1][0] for c in m.tutor.chamadas if c[0] == "explain"][-2:] == ["stall", "stall"]


async def test_praticar_palavra_que_nao_existe() -> None:
    m = montar()

    (resposta,) = await m.diz("/practice hedge")

    assert 'couldn\'t find "hedge"' in resposta


async def test_praticar_sem_pendentes() -> None:
    m = montar()

    (resposta,) = await m.diz("/practice")

    assert "No pending words" in resposta


async def test_apagar_remove_a_entrada_e_as_frases() -> None:
    m = await _stall_e_hedge()

    (resposta,) = await m.diz("/delete stall")

    assert "🗑️ *stall* deleted." in resposta
    assert m.repo.obter_entrada("stall") is None
    assert m.repo.listar_frases("stall") == []
    assert len(m.repo.listar_entradas()) == 1


async def test_apagar_a_palavra_em_andamento_zera_a_sessao() -> None:
    m = montar(tutor=FakeTutor(explicacoes=[explicacao_stall()]))
    await m.diz("stall")

    await m.diz("/apagar stall")

    sessao = m.repo.obter_sessao()
    assert sessao.estado == Estado.IDLE
    assert sessao.entry_id is None


async def test_apagar_sem_argumento_ou_inexistente() -> None:
    m = montar()

    (sem_argumento,) = await m.diz("/delete")
    (inexistente,) = await m.diz("/delete hedge")

    assert "I don't know" in sem_argumento
    assert 'couldn\'t find "hedge"' in inexistente


async def test_nivel_mostra_e_altera() -> None:
    m = montar()

    (atual,) = await m.diz("/level")
    (alterado,) = await m.diz("/level b2-c1")
    (depois,) = await m.diz("/level")

    assert "*B1-B2*" in atual
    assert "set to *B2-C1*" in alterado
    assert "*B2-C1*" in depois
    perfil = m.repo.obter_perfil()
    assert perfil is not None
    assert perfil.nivel == "B2-C1"


async def test_nivel_invalido_nao_muda() -> None:
    m = montar()

    (resposta,) = await m.diz("/level C2")

    assert "Invalid level" in resposta
    perfil = m.repo.obter_perfil()
    assert perfil is not None
    assert perfil.nivel == "B1-B2"


async def test_cancelar_volta_para_idle_sem_apagar_nada() -> None:
    m = montar(tutor=FakeTutor(explicacoes=[explicacao_stall()]))
    await m.diz("stall")

    (resposta,) = await m.diz("/cancel")

    assert "still saved" in resposta
    assert m.repo.obter_sessao().estado == Estado.IDLE
    assert m.repo.obter_entrada("stall") is not None


async def test_comando_no_meio_do_fluxo_nao_desmonta_a_sessao() -> None:
    m = montar(tutor=FakeTutor(explicacoes=[explicacao_stall()]))
    await m.diz("stall")

    await m.diz("/help")

    assert m.repo.obter_sessao().estado == Estado.AWAIT_ACTION


async def test_status_mostra_waha_e_contagens() -> None:
    async def status() -> str:
        return "WORKING"

    m = await _stall_e_hedge()
    m.router._status_da_sessao = status

    (resposta,) = await m.diz("/status")

    assert "WAHA): WORKING" in resposta
    assert "Words: 2" in resposta
    assert "Pending: 1" in resposta


async def test_status_funciona_mesmo_com_o_waha_fora() -> None:
    async def status() -> str:
        raise ConnectionError("fora")

    m = montar(status_da_sessao=status)

    (resposta,) = await m.diz("/status")

    assert "WAHA): unavailable" in resposta


@dataclass
class ExportadorFalso:
    resultado: ResultadoExportacao | None
    chamadas: list[bool] = field(default_factory=list)

    def exportar(self, *, tudo: bool) -> ResultadoExportacao | None:
        self.chamadas.append(tudo)
        return self.resultado


async def test_exportar_devolve_o_link() -> None:
    exportador = ExportadorFalso(ResultadoExportacao("https://exemplo.test/anki.txt", 4, 0))
    m = montar(exportador=exportador)

    (resposta,) = await m.diz("/export")

    assert "4 cards" in resposta
    assert "https://exemplo.test/anki.txt" in resposta
    assert exportador.chamadas == [False]


async def test_exportar_tudo_pede_tudo() -> None:
    exportador = ExportadorFalso(ResultadoExportacao("https://exemplo.test/anki.txt", 9, 2))
    m = montar(exportador=exportador)

    (resposta,) = await m.diz("/export all")

    assert exportador.chamadas == [True]
    assert "2 word(s) were left out" in resposta


async def test_exportar_tudo_aceita_o_apelido_em_pt_br() -> None:
    exportador = ExportadorFalso(ResultadoExportacao("https://exemplo.test/anki.txt", 1, 0))
    m = montar(exportador=exportador)

    await m.diz("/exportar tudo")

    assert exportador.chamadas == [True]


async def test_exportar_sem_nada_novo() -> None:
    m = montar(exportador=ExportadorFalso(None))

    (resposta,) = await m.diz("/export")

    assert "nothing new to export" in resposta


async def test_exportar_sem_exportador_configurado() -> None:
    m = montar()

    (resposta,) = await m.diz("/export")

    assert "isn't available" in resposta
