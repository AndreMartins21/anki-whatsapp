"""Testes dos comandos (seção 5.2, M9: nomes em inglês + apelido em PT-BR)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from app import messages
from app.domain.models import (
    Entry,
    Estado,
    Explanation,
    Roteamento,
    Sense,
    SentidoSalvo,
    Synonym,
)
from app.services.fake_llm import FakeTutor
from app.services.planilha import ResultadoExportacao
from tests.helpers import T0, Montagem, avaliacao, expansoes, explicacao_stall, montar

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
        "/info",
        "/pending",
        "/practice",
        "/review",
        "/reminders",
        "/profile",
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
    # o relógio de teste é fixo: o desempate por slug põe "hedge" antes de "stall"
    assert "1. 🆕 hedge — proteger-se" in resposta
    assert "2. ✅ stall — travar, emperrar" in resposta


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
    chamadas: int = 0

    def exportar(self) -> ResultadoExportacao | None:
        self.chamadas += 1
        return self.resultado


async def test_exportar_devolve_o_link() -> None:
    exportador = ExportadorFalso(ResultadoExportacao("https://exemplo.test/vocabot.xlsx", 4))
    m = montar(exportador=exportador)

    (resposta,) = await m.diz("/export")

    assert "4 words in the spreadsheet" in resposta
    assert "https://exemplo.test/vocabot.xlsx" in resposta
    assert exportador.chamadas == 1


async def test_exportar_all_e_o_apelido_em_pt_br_continuam_aceitos() -> None:
    exportador = ExportadorFalso(ResultadoExportacao("https://exemplo.test/vocabot.xlsx", 1))
    m = montar(exportador=exportador)

    await m.diz("/export all")
    await m.diz("/exportar tudo")

    assert exportador.chamadas == 2


async def test_exportar_sem_nada() -> None:
    m = montar(exportador=ExportadorFalso(None))

    (resposta,) = await m.diz("/export")

    assert "nothing to export" in resposta


async def test_exportar_sem_exportador_configurado() -> None:
    m = montar()

    (resposta,) = await m.diz("/export")

    assert "isn't available" in resposta


# ---- /lembretes (M10) --------------------------------------------------------------------------


async def test_lembretes_desligados_por_padrao() -> None:
    m = montar()

    (resposta,) = await m.diz("/lembretes")

    assert "off" in resposta.lower()


async def test_lembretes_liga_com_a_janela_padrao() -> None:
    m = montar()

    (resposta,) = await m.diz("/lembretes 3")

    assert "3x a day" in resposta
    assert "9h" in resposta and "21h" in resposta
    perfil = m.repo.obter_perfil()
    assert perfil is not None
    assert (perfil.lembretes_por_dia, perfil.janela_inicio, perfil.janela_fim) == (3, 9, 21)


async def test_lembretes_liga_com_janela_propria() -> None:
    m = montar()

    (resposta,) = await m.diz("/lembretes 2 20h-23h")

    assert "20h" in resposta and "23h" in resposta
    perfil = m.repo.obter_perfil()
    assert perfil is not None
    assert (perfil.lembretes_por_dia, perfil.janela_inicio, perfil.janela_fim) == (2, 20, 23)


async def test_lembretes_desliga() -> None:
    m = montar()
    await m.diz("/lembretes 3")

    (resposta,) = await m.diz("/lembretes off")

    assert "off" in resposta.lower()
    perfil = m.repo.obter_perfil()
    assert perfil is not None
    assert perfil.lembretes_por_dia == 0


async def test_lembretes_argumento_invalido() -> None:
    m = montar()

    (resposta,) = await m.diz("/lembretes 99")

    assert "couldn't understand" in resposta
    perfil = m.repo.obter_perfil()
    assert perfil is not None
    assert perfil.lembretes_por_dia == 0


async def test_lembretes_atuais_mostra_o_que_esta_configurado() -> None:
    m = montar()
    await m.diz("/lembretes 3 9h-22h")

    (resposta,) = await m.diz("/lembretes")

    assert "3x a day" in resposta
    assert "9h" in resposta and "22h" in resposta


# ---- /list paginado, /info e /profile (M12) --------------------------------------------------


def _preencher_entradas(m: Montagem, quantidade: int) -> None:
    for i in range(quantidade):
        m.repo.criar_entrada(
            Entry(
                slug=f"w{i:02d}",
                palavra=f"word{i:02d}",
                classe="noun",
                cefr_estimado="B1",
                sentido=SentidoSalvo(traducao=f"palavra {i}", definicao="a thing"),
                criado_em=T0 + timedelta(minutes=i),
                atualizado_em=T0,
            )
        )


async def test_lista_pagina_de_20_com_numeracao_global() -> None:
    m = montar()
    _preencher_entradas(m, 25)

    (primeira,) = await m.diz("/list")
    (segunda,) = await m.diz("/list 2")

    assert "*Your words* (25)" in primeira
    assert "1. 🆕 word00" in primeira
    assert "20. 🆕 word19" in primeira
    assert "21." not in primeira
    assert "Page 1/2 — /list 2 for more" in primeira
    assert "21. 🆕 word20" in segunda
    assert "25. 🆕 word24" in segunda
    assert "/info 21 for details" in segunda
    assert "Page 2/2" in segunda
    assert "for more" not in segunda


async def test_lista_curta_nao_mostra_pagina() -> None:
    m = await _stall_e_hedge()

    (resposta,) = await m.diz("/list")

    assert "Page" not in resposta


async def test_lista_pagina_invalida() -> None:
    m = await _stall_e_hedge()

    for argumento in ("2", "0", "abc"):
        (resposta,) = await m.diz(f"/list {argumento}")
        assert "That page doesn't exist" in resposta


async def test_info_por_numero_mostra_frases_corrigidas_exemplos_e_sinonimos() -> None:
    m = montar(
        tutor=FakeTutor(
            explicacoes=[explicacao_stall()],
            roteamentos=[_roteamento_frase()],
            sinonimos=[
                [
                    Synonym(
                        expressao="stumble",
                        significado="to lose momentum",
                        exemplo="It [[stumbled]].",
                    )
                ]
            ],
            expansoes=[expansoes()],
        )
    )
    await m.diz("stall | the talks stalled")
    await m.diz("2")  # synonyms
    await m.diz("the project stalled")
    await m.diz("3")  # save

    (resposta,) = await m.diz("/info 1")

    assert resposta.startswith("*1. stall* (verb) — B2")
    assert "🇧🇷 travar, emperrar" in resposta
    assert "↔️ enrolar — to delay on purpose" in resposta
    # a frase do aluno aparece já corrigida, sem [[ ]]
    assert "• The project stalled because the client didn't send the documents." in resposta
    assert "[[" not in resposta
    assert "📝 *Examples*\n• The talks stalled." in resposta
    assert "🔄 *Synonyms*\n• *stumble* = to lose momentum" in resposta


async def test_info_por_palavra_e_pelo_apelido() -> None:
    m = await _stall_e_hedge()

    (por_palavra,) = await m.diz("/info hedge")

    assert por_palavra.startswith("*2. hedge*") or por_palavra.startswith("*1. hedge*")
    assert "proteger-se" in por_palavra


async def test_info_sem_argumento_ou_inexistente() -> None:
    m = await _stall_e_hedge()

    (sem_argumento,) = await m.diz("/info")
    (numero_fora,) = await m.diz("/info 9")
    (inexistente,) = await m.diz("/info banana")

    assert "Tell me which word" in sem_argumento
    assert "couldn't find" in numero_fora
    assert "couldn't find" in inexistente


async def test_practice_e_delete_aceitam_o_numero_da_lista() -> None:
    m = await _stall_e_hedge()

    # a ordem é a da /list: hedge (1) e stall (2)
    (resposta,) = await m.diz("/delete 1")

    assert "🗑️ *hedge* deleted." in resposta
    assert [e.slug for e in m.repo.listar_entradas()] == ["stall"]


async def test_profile_com_lembretes_desligados() -> None:
    m = await _stall_e_hedge()

    (resposta,) = await m.diz("/profile")

    assert "Level: B1-B2" in resposta
    assert "Words: 2 (1 practiced, 1 pending)" in resposta
    assert "Due for review: 2" in resposta
    assert "Reminders: off — turn them on with /reminders 3" in resposta


async def test_profile_com_lembretes_ligados_mostra_todo_dia() -> None:
    m = montar()
    await m.diz("/reminders 3 9h-22h")

    (resposta,) = await m.diz("/perfil")

    assert "Words: 0 (0 practiced, 0 pending)" in resposta
    assert "Reminders: every day, 3x between 9h and 22h" in resposta


def test_nenhuma_mensagem_divulga_o_nome_em_portugues() -> None:
    fonte = Path(messages.__file__).read_text(encoding="utf-8")

    assert not re.search(r"/(lista|praticar|lembretes|revisar|exportar|apagar|ajuda)\b", fonte)
