"""M16 (ADR-0019): o bot no grupo. Só reage ao prefixo, conjunto fechado de comandos, respostas
dentro de uma atividade, papéis, e nunca chama a IA fora de atividade. Sem rede, sem credencial."""

from __future__ import annotations

import re

import pytest

from app import messages
from app.domain.models import Estado, Roteamento
from app.flows.base import Autor
from app.services.fake_llm import FakeTutor
from tests.helpers import (
    ANA,
    BIA,
    CAIO,
    CHAT,
    DONO_NUMERO,
    GRUPO,
    Montagem,
    expansoes,
    explicacao_stall,
    montar,
)
from tests.test_flows import EXEMPLOS, SINONIMOS, _roteamento_frase

# `/comando` colado a uma palavra: um comando do privado citado (URLs e "and/or" não contam).
_CITA_COMANDO_DO_PRIVADO = re.compile(r"(?<![\w/])/[a-z]{3,}")
_COMANDOS_CITADOS = re.compile(r"(?<![\w!])!([a-z]{3,})")
_DO_GRUPO = {"add", "list", "practice", "review", "reminder", "reminders", "group", "help"}


def _tutor() -> FakeTutor:
    return FakeTutor(
        explicacoes=[explicacao_stall(), explicacao_stall()],
        exemplos=[EXEMPLOS],
        sinonimos=[SINONIMOS],
        expansoes=[expansoes()],
        roteamentos=[_roteamento_frase("quase")],
    )


def _sem_comandos_do_privado(textos: list[str]) -> None:
    for texto in textos:
        assert not _CITA_COMANDO_DO_PRIVADO.search(texto), texto
        for comando in _COMANDOS_CITADOS.findall(texto):
            assert comando in _DO_GRUPO | {"activate"}, (comando, texto)


def _grupo() -> Montagem:
    return montar(tutor=_tutor())


# --- só o prefixo é lido ----------------------------------------------------------------------


async def test_mensagem_sem_prefixo_e_conversa_e_nada_acontece() -> None:
    m = _grupo()

    respostas = await m.diz_no_grupo(ANA, "gente, alguém entendeu a aula de hoje?")

    assert respostas == []
    assert m.tutor.chamadas == []
    assert m.banco.do_espaco(GRUPO).listar_membros() == []  # nem o cadastro do autor


async def test_prefixo_configuravel() -> None:
    m = montar(tutor=_tutor(), prefixo_do_grupo="#")

    assert await m.diz_no_grupo(ANA, "!add stall") == []  # o "!" não vale mais
    ajuda = await m.diz_no_grupo(ANA, "#help")

    assert "#add" in ajuda[0] and "!add" not in ajuda[0]


async def test_privado_nao_ve_o_grupo_e_grupo_nao_ve_o_privado() -> None:
    m = _grupo()
    await m.diz_no_grupo(ANA, "!add stall")

    assert m.banco.do_espaco(CHAT).listar_entradas() == []
    assert len(m.banco.do_espaco(GRUPO).listar_entradas()) == 1


@pytest.mark.parametrize("texto", ["!", "!!!", "! add stall", "!?", "!  ", "!!! wow"])
async def test_exclamacao_sem_letra_ou_numero_depois_e_conversa_e_nao_chama_o_bot(
    texto: str,
) -> None:
    m = _grupo()

    assert await m.diz_no_grupo(ANA, texto) == []
    assert m.tutor.chamadas == []
    assert m.banco.do_espaco(GRUPO).listar_membros() == []


# --- !add e o ciclo da palavra ----------------------------------------------------------------


async def test_add_traz_o_card_com_o_menu_no_prefixo_do_grupo() -> None:
    m = _grupo()

    (card,) = await m.diz_no_grupo(ANA, "!add stall | the talks stalled")

    assert "*stall*" in card
    assert "!1 — Hear how it sounds" in card and "!2 — See more examples" in card
    assert "!4 — Just save" in card
    assert "start it with !" in card
    assert m.banco.do_espaco(GRUPO).obter_sessao().estado == Estado.AWAIT_ACTION
    _sem_comandos_do_privado([card])


async def test_add_de_palavra_que_ja_existe_avisa_com_o_prefixo_e_0_libera() -> None:
    m = _grupo()
    await m.diz_no_grupo(ANA, "!add stall")
    await m.diz_no_grupo(BIA, "!0")

    (aviso,) = await m.diz_no_grupo(BIA, "!add stall")

    assert aviso.startswith("📌 You already have *stall* in your list.")
    assert "!1 — Hear how it sounds" in aviso and "!3 — Check synonyms" in aviso
    assert "!4" not in aviso
    assert "type !0 or !skip" in aviso
    assert m.banco.do_espaco(GRUPO).obter_sessao().estado == Estado.AWAIT_ACTION
    (fim,) = await m.diz_no_grupo(BIA, "!skip")
    assert fim.startswith("Alright!")
    assert m.banco.do_espaco(GRUPO).obter_sessao().estado == Estado.IDLE


async def test_opcao_4_no_grupo_descarta_a_palavra_recem_criada() -> None:
    m = _grupo()
    await m.diz_no_grupo(ANA, "!add stall")

    (resposta,) = await m.diz_no_grupo(BIA, "!5")

    assert resposta.startswith("🗑️ Ignored *stall*")
    assert m.banco.do_espaco(GRUPO).obter_entrada("stall") is None


async def test_ciclo_completo_stall_com_dois_alunos() -> None:
    m = _grupo()
    await m.diz_no_grupo(ANA, "!add stall | the talks stalled")

    exemplos = await m.diz_no_grupo(BIA, "!2")
    avaliacao = await m.diz_no_grupo(ANA, "!The project stalled because the client didn't send it")
    salvo = await m.diz_no_grupo(BIA, "!4")

    assert "Examples with stall" in exemplos[0]
    assert "Almost there" in avaliacao[0]
    assert "Saved: *stall*" in salvo[0] and "!practice stall" in salvo[0] and "!list" in salvo[0]
    for texto in (*exemplos, *avaliacao, *salvo):
        _sem_comandos_do_privado([texto])
    repo = m.banco.do_espaco(GRUPO)
    assert repo.obter_sessao().estado == Estado.IDLE
    (entrada,) = repo.listar_entradas()
    assert entrada.status == "praticada"


async def test_a_frase_guarda_quem_escreveu() -> None:
    m = _grupo()
    await m.diz_no_grupo(ANA, "!add stall")

    await m.diz_no_grupo(BIA, "!The project stalled because the client didn't send it")

    frases = m.banco.do_espaco(GRUPO).listar_frases("stall")
    do_usuario = [f for f in frases if f.autor == "usuario"]
    assert [f.autor_id for f in do_usuario] == [BIA.numero]
    assert all(f.autor_id is None for f in frases if f.autor == "bot")


async def test_sinonimos_pelo_menu_3() -> None:
    m = _grupo()
    await m.diz_no_grupo(ANA, "!add stall")

    (resposta,) = await m.diz_no_grupo(CAIO, "!3")

    assert "Synonyms for stall" in resposta and "!4 — Just save" in resposta


async def test_add_sem_palavra_explica_o_uso() -> None:
    m = _grupo()

    assert await m.diz_no_grupo(ANA, "!add") == [messages.grupo_add_uso("!")]
    assert m.tutor.chamadas == []


async def test_add_com_outra_palavra_aberta_salva_a_anterior_antes() -> None:
    m = _grupo()
    await m.diz_no_grupo(ANA, "!add stall")
    m.tutor.explicacoes[:] = [explicacao_stall().model_copy(update={"palavra": "hedge"})]
    m.tutor.expansoes[:] = [expansoes()]

    respostas = await m.diz_no_grupo(BIA, "!add hedge")

    assert "Saved: *stall*" in respostas[0]
    assert "*hedge*" in respostas[-1]
    assert sorted(e.slug for e in m.banco.do_espaco(GRUPO).listar_entradas()) == ["hedge", "stall"]


async def test_palavra_nova_pelo_roteamento_no_grupo_so_da_a_dica_do_add() -> None:
    tutor = _tutor()
    tutor.roteamentos = [Roteamento(intencao="nova_palavra", palavra="hedge")]
    m = montar(tutor=tutor)
    await m.diz_no_grupo(ANA, "!add stall")

    respostas = await m.diz_no_grupo(BIA, "!hedge")

    assert respostas == [messages.nova_palavra_no_grupo("!")]
    assert [e.slug for e in m.banco.do_espaco(GRUPO).listar_entradas()] == ["stall"]  # nada aberto
    assert m.banco.do_espaco(GRUPO).obter_sessao().estado == Estado.AWAIT_ACTION


# --- fora de atividade: sem IA ----------------------------------------------------------------


@pytest.mark.parametrize("texto", ["!stall", "!hello there", "!1", "!yes"])
async def test_texto_com_prefixo_fora_de_atividade_recebe_a_ajuda_sem_chamar_a_ia(
    texto: str,
) -> None:
    m = _grupo()

    respostas = await m.diz_no_grupo(ANA, texto)

    assert respostas == [messages.ajuda_do_grupo("!")]
    assert m.tutor.chamadas == []


@pytest.mark.parametrize(
    "comando",
    [
        "!export",
        "!level B2-C1",
        "!song paper plane",
        "!info 1",
        "!status",
        "!delete stall",
        "!cancel",
        "!pending",
        "!profile",
    ],
)
async def test_comando_do_privado_no_grupo_e_recusado_com_a_ajuda_do_grupo(comando: str) -> None:
    m = _grupo()

    respostas = await m.diz_no_grupo(ANA, comando)

    assert respostas == [messages.ajuda_do_grupo("!")]
    assert m.tutor.chamadas == []
    _sem_comandos_do_privado(respostas)


async def test_comando_do_privado_com_barra_no_grupo_nem_e_lido() -> None:
    m = _grupo()

    assert await m.diz_no_grupo(ANA, "/list") == []
    assert await m.diz_no_grupo(ANA, "/export") == []


async def test_a_ajuda_do_grupo_so_cita_comandos_do_grupo() -> None:
    m = _grupo()

    (ajuda,) = await m.diz_no_grupo(ANA, "!help")

    _sem_comandos_do_privado([ajuda])
    for comando in ("add", "list", "practice", "review", "reminder", "group"):
        assert f"!{comando}" in ajuda
    for escondido in ("teacher", "student", "activate"):
        assert escondido not in ajuda
    for do_privado in ("export", "song", "level", "delete", "cancel", "status", "pending"):
        assert f"!{do_privado}" not in ajuda and f"/{do_privado}" not in ajuda


# --- !list, !practice -------------------------------------------------------------------------


async def test_list_vazio_e_com_palavras_no_titulo_da_turma() -> None:
    m = _grupo()
    assert await m.diz_no_grupo(ANA, "!list") == [messages.sem_entradas("!")]

    await m.diz_no_grupo(ANA, "!add stall")
    await m.diz_no_grupo(ANA, "!4")
    (lista,) = await m.diz_no_grupo(BIA, "!list")

    assert "The class's words" in lista and "1. stall" in lista
    assert "!practice 1 to practice one" in lista
    assert "!info" not in lista
    _sem_comandos_do_privado([lista])


async def test_list_pagina_invalida_cita_o_prefixo_do_grupo() -> None:
    m = _grupo()
    await m.diz_no_grupo(ANA, "!add stall")

    (resposta,) = await m.diz_no_grupo(ANA, "!list 9")

    assert resposta == messages.pagina_invalida("!")


async def test_practice_retoma_uma_palavra_do_caderno_da_turma() -> None:
    m = _grupo()
    await m.diz_no_grupo(ANA, "!add stall")
    await m.diz_no_grupo(ANA, "!4")

    (card,) = await m.diz_no_grupo(BIA, "!practice stall")

    assert "*stall*" in card and "!2 — See more examples" in card


async def test_practice_por_numero_e_palavra_inexistente() -> None:
    m = _grupo()
    await m.diz_no_grupo(ANA, "!add stall")
    await m.diz_no_grupo(ANA, "!4")
    m.tutor.explicacoes.append(explicacao_stall())

    assert "*stall*" in (await m.diz_no_grupo(BIA, "!practice 1"))[0]
    nao_achou = (await m.diz_no_grupo(BIA, "!practice zzz"))[0]
    assert "the class's words" in nao_achou and "!list" in nao_achou
    _sem_comandos_do_privado([nao_achou])


# --- !reminder --------------------------------------------------------------------------------


async def test_reminder_configura_os_lembretes_do_grupo() -> None:
    m = _grupo()

    (ligado,) = await m.diz_no_grupo(ANA, "!reminder 3 9h-22h")

    assert "Reminders set: 3x a day, between 9h and 22h" in ligado
    perfil = m.banco.do_espaco(GRUPO).obter_perfil()
    assert perfil is not None and perfil.lembretes_por_dia == 3
    assert m.banco.do_espaco(CHAT).obter_perfil() is None  # o privado de ninguém mudou


async def test_reminder_sem_argumento_off_alias_e_invalido_citam_o_prefixo_do_grupo() -> None:
    m = _grupo()

    atual = (await m.diz_no_grupo(ANA, "!reminder"))[0]
    invalido = (await m.diz_no_grupo(ANA, "!reminders blah"))[0]
    await m.diz_no_grupo(ANA, "!reminders 2")
    desligado = (await m.diz_no_grupo(ANA, "!reminder off"))[0]

    assert "!reminder 3" in atual
    assert "!reminder 3 9h-22h" in invalido
    assert "off" in desligado
    _sem_comandos_do_privado([atual, invalido, desligado])
    perfil = m.banco.do_espaco(GRUPO).obter_perfil()
    assert perfil is not None and perfil.lembretes_por_dia == 0


async def test_a_dica_de_lembretes_do_grupo_cita_o_comando_do_grupo() -> None:
    m = _grupo()
    await m.diz_no_grupo(ANA, "!add stall")

    (salvo,) = await m.diz_no_grupo(ANA, "!4")

    assert "Send !reminder 3" in salvo
    _sem_comandos_do_privado([salvo])


# --- membros, papéis e !group -----------------------------------------------------------------


async def test_quem_manda_a_primeira_mensagem_com_prefixo_entra_como_aluno() -> None:
    m = _grupo()

    await m.diz_no_grupo(ANA, "!help")

    membro = m.banco.do_espaco(GRUPO).obter_membro(ANA.numero)
    assert membro is not None and (membro.papel, membro.nome) == ("aluno", "Ana")


async def test_o_nome_do_whatsapp_atualiza_o_cadastro() -> None:
    m = _grupo()
    await m.diz_no_grupo(Autor(ANA.numero, None), "!help")
    await m.diz_no_grupo(ANA, "!help")

    assert m.banco.do_espaco(GRUPO).obter_membro(ANA.numero).nome == "Ana"  # type: ignore[union-attr]


async def test_teacher_pelo_dono_com_o_numero_escrito() -> None:
    m = _grupo()
    dono = Autor(DONO_NUMERO, "Dono")

    (resposta,) = await m.diz_no_grupo(dono, f"!teacher {BIA.numero}")

    assert resposta == messages.papel_alterado(None, "professor")
    assert m.banco.do_espaco(GRUPO).obter_membro(BIA.numero).papel == "professor"  # type: ignore[union-attr]


async def test_teacher_com_mencao_do_payload_e_nome_do_membro_ja_conhecido() -> None:
    m = _grupo()
    await m.diz_no_grupo(BIA, "!help")
    dono = Autor(DONO_NUMERO, "Dono", mencionados=(BIA.numero,))

    (resposta,) = await m.diz_no_grupo(dono, "!teacher @Bia")

    assert resposta == messages.papel_alterado("Bia", "professor")


async def test_um_professor_promove_e_rebaixa_outros() -> None:
    m = _grupo()
    await m.diz_no_grupo(Autor(DONO_NUMERO, "Dono"), f"!teacher {ANA.numero}")

    await m.diz_no_grupo(ANA, f"!teacher {BIA.numero}")
    assert m.banco.do_espaco(GRUPO).obter_membro(BIA.numero).papel == "professor"  # type: ignore[union-attr]

    (resposta,) = await m.diz_no_grupo(ANA, f"!student {BIA.numero}")
    assert resposta == messages.papel_alterado(None, "aluno")
    assert m.banco.do_espaco(GRUPO).obter_membro(BIA.numero).papel == "aluno"  # type: ignore[union-attr]


async def test_aluno_que_tenta_teacher_recebe_a_resposta_de_comando_desconhecido() -> None:
    m = _grupo()
    await m.diz_no_grupo(ANA, "!help")

    respostas = await m.diz_no_grupo(ANA, f"!teacher {ANA.numero}")

    assert respostas == [messages.ajuda_do_grupo("!")]
    assert m.banco.do_espaco(GRUPO).obter_membro(ANA.numero).papel == "aluno"  # type: ignore[union-attr]


async def test_teacher_tolera_o_nono_digito_e_nao_duplica_o_membro() -> None:
    m = _grupo()
    await m.diz_no_grupo(Autor("553199998888", "Ana"), "!help")  # a conta sem o 9
    dono = Autor(DONO_NUMERO, "Dono")

    await m.diz_no_grupo(dono, "!teacher 5531999998888")  # o mesmo número, com o 9

    membros = m.banco.do_espaco(GRUPO).listar_membros()
    da_ana = [(n, mb.papel) for n, mb in membros if n.startswith("55319999")]
    assert da_ana == [("553199998888", "professor")]  # um só cadastro, o do número sem o 9


async def test_teacher_sem_alvo_explica_o_uso_e_os_papeis_nao_aparecem_no_help() -> None:
    m = _grupo()

    (resposta,) = await m.diz_no_grupo(Autor(DONO_NUMERO, "Dono"), "!teacher")

    assert resposta == messages.papel_uso("teacher", "!")


async def test_group_mostra_a_turma_sem_telefone() -> None:
    m = _grupo()
    await m.diz_no_grupo(ANA, "!add stall")
    await m.diz_no_grupo(ANA, "!4")
    await m.diz_no_grupo(BIA, "!help")
    await m.diz_no_grupo(Autor(CAIO.numero, None), "!help")
    await m.diz_no_grupo(Autor(DONO_NUMERO, "Prof"), f"!teacher {BIA.numero}")

    (resposta,) = await m.diz_no_grupo(ANA, "!group")

    assert "Your class" in resposta and "Level: B1-B2" in resposta
    assert "Words: 1" in resposta
    assert "• Ana (student)" in resposta
    assert "• Bia (teacher)" in resposta
    assert "• Student 1 (student)" in resposta  # sem nome: nunca o número
    for telefone in (ANA.numero, BIA.numero, CAIO.numero, DONO_NUMERO):
        assert telefone not in resposta
    assert "@" not in resposta  # sem menção: não notifica ninguém
    _sem_comandos_do_privado([resposta])


async def test_group_com_lembretes_mostra_o_proximo_horario() -> None:
    m = _grupo()
    await m.diz_no_grupo(ANA, "!reminder 3 9h-22h")

    (resposta,) = await m.diz_no_grupo(ANA, "!group")

    assert "every day, 3x between 9h and 22h" in resposta and "Next reminder" in resposta


# --- limite de mensagens e privado ------------------------------------------------------------


async def test_qualquer_mensagem_com_prefixo_de_qualquer_participante_conta_como_resposta() -> None:
    m = _grupo()
    conversa = m.router.conversa_do(GRUPO)
    for _ in range(3):
        await conversa.enviar("bot fala sozinho")
    antes = len(m.channel.textos_enviados)
    await conversa.enviar("a quarta seria descartada")
    assert len(m.channel.textos_enviados) == antes

    respostas = await m.diz_no_grupo(CAIO, "!help")  # outro participante fala

    assert respostas == [messages.ajuda_do_grupo("!")]


async def test_o_apelido_exclamacao_no_privado_vale_a_barra() -> None:
    m = _grupo()
    await m.diz("stall")
    await m.diz("4")

    lista_com_barra = await m.diz("/list")
    lista_com_exclamacao = await m.diz("!list")

    assert lista_com_exclamacao == lista_com_barra
    assert "Your words" in lista_com_exclamacao[0]  # o título do privado, não o da turma


async def test_no_privado_exclamacao_sem_letra_continua_sendo_texto() -> None:
    m = _grupo()
    await m.diz("stall")

    await m.diz("!!! wow")  # não é comando: vai para a IA como a frase de sempre

    assert m.tutor.chamadas[-1][0] == "route"


async def test_o_privado_segue_sem_prefixo_e_com_a_barra() -> None:
    m = _grupo()

    (card,) = await m.diz("stall")

    assert "Now, you can write one or more sentences using *stall*" in card
    assert "!1" not in card


# --- lembretes do grupo (o agendador) ---------------------------------------------------------


def _agendador_do_grupo(m: Montagem, *, autorizado: bool = True):  # type: ignore[no-untyped-def]
    from zoneinfo import ZoneInfo

    from app.services.lembretes import Agendador

    async def dormir(_: float) -> None:
        return None

    return Agendador(
        router=m.router,
        banco=m.banco,
        agora=m.relogio.agora,
        fuso=ZoneInfo("UTC"),
        dormir=dormir,
        grupo_autorizado=lambda _grupo: autorizado,
    )


def _grupo_com_lembrete_e_palavra_vencida(m: Montagem) -> None:
    from datetime import timedelta

    from app.domain.models import Membro, Profile
    from tests.helpers import T0
    from tests.test_agendador import _entrada_vencida

    espaco = m.banco.do_espaco(GRUPO)
    espaco.salvar_membro(ANA.numero, Membro(nome="Ana", entrou_em=T0))  # M17: alguém para marcar
    espaco.criar_entrada(_entrada_vencida())
    espaco.salvar_perfil(
        Profile(nivel="B1-B2", chat_id=GRUPO, lembretes_por_dia=3, proximo_lembrete=T0)
    )
    m.relogio.avancar(timedelta(seconds=1))


async def test_o_lembrete_do_grupo_inicia_a_revisao_no_grupo_com_o_prefixo_do_grupo() -> None:
    m = _grupo()
    _grupo_com_lembrete_e_palavra_vencida(m)

    await _agendador_do_grupo(m)._tick()

    ((chat, texto),) = m.channel.textos_enviados
    assert chat == GRUPO
    assert "Practice time" in texto and "Anyone can type !0 to leave the practice" in texto
    _sem_comandos_do_privado([texto])
    assert m.banco.do_espaco(GRUPO).obter_sessao().estado == Estado.REVIEWING


async def test_grupo_desativado_nao_recebe_lembrete() -> None:
    m = _grupo()
    _grupo_com_lembrete_e_palavra_vencida(m)

    await _agendador_do_grupo(m, autorizado=False)._tick()

    assert m.channel.textos_enviados == []


async def test_o_lembrete_de_um_aluno_no_privado_continua_igual() -> None:
    from app.domain.models import Profile
    from tests.helpers import T0
    from tests.test_agendador import _entrada_vencida

    m = _grupo()
    m.repo.criar_entrada(_entrada_vencida())
    m.repo.salvar_perfil(
        Profile(nivel="B1-B2", chat_id=CHAT, lembretes_por_dia=3, proximo_lembrete=T0)
    )

    await _agendador_do_grupo(m, autorizado=False)._tick()  # o filtro é só de grupos

    ((chat, texto),) = m.channel.textos_enviados
    assert chat == CHAT and "Type 0 to leave the practice" in texto
