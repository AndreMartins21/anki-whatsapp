"""Testes de ponta a ponta dos fluxos (M4), com FakeTutor, FakeChannel e MemoryRepository."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.domain.models import Estado
from app.services.fake_llm import FakeTutor
from app.services.llm import LLMError
from tests.helpers import (
    CHAT,
    avaliacao,
    expansoes,
    explicacao_stall,
    montar,
)

EXEMPLOS = ["The talks [[stalled]] again.", "My car [[stalled]].", "Don't [[stall]] me."]


def _tutor_completo() -> FakeTutor:
    return FakeTutor(
        explicacoes=[explicacao_stall()],
        avaliacoes=[avaliacao("quase")],
        exemplos=[EXEMPLOS],
        expansoes=[expansoes()],
    )


# ---- o ciclo "stall" da spec, do começo ao fim ---------------------------------------------


async def test_ciclo_completo_do_stall() -> None:
    m = montar(tutor=_tutor_completo())

    # 1-2. O aluno manda a palavra com a frase; o sentido vem do contexto, então há menu direto.
    (explicacao,) = await m.diz("stall | the talks stalled")
    assert explicacao == (
        "*STALL* (verbo) · B2\n"
        "🇧🇷 travar, emperrar\n"
        "📖 to stop making progress\n"
        '💡 "the car stalled" = o carro morreu\n'
        "\n"
        "O que você quer fazer?\n"
        "1️⃣ Escrever uma frase\n"
        "2️⃣ Ver exemplos\n"
        "3️⃣ Só salvar\n"
        '_(ou já mande sua frase com "stall")_'
    )
    assert m.repo.obter_sessao().estado == Estado.AWAIT_CHOICE

    # 3-4. Escolhe escrever e manda a frase; recebe a avaliação e o menu seguinte.
    (pedido,) = await m.diz("1")
    assert "stall" in pedido
    (avaliada,) = await m.diz("The project stalled because the client didn't sent the documents.")
    assert avaliada == (
        "⚠️ *Quase lá!* O sentido está certo.\n"
        "✏️ didn't sent → didn't send\n"
        "✨ The project stalled because the client didn't send the documents.\n"
        '💬 Depois de "didn\'t", o verbo fica na forma base.\n'
        "\n"
        "1️⃣ Outra frase  ·  2️⃣ Exemplos  ·  3️⃣ Concluir"
    )
    assert m.repo.obter_sessao().estado == Estado.AWAIT_NEXT

    # 5. Pede exemplos: 3 frases e o convite para escrever a dela.
    (exemplos,) = await m.diz("2")
    assert exemplos.startswith("📝 *Exemplos de stall*")
    assert "1. The talks stalled again." in exemplos
    assert "[[" not in exemplos
    assert m.repo.obter_sessao().estado == Estado.AWAIT_AFTER_EXAMPLES

    # 6-7. Conclui: fica salvo (praticada) e vêm as expansões.
    (salvo,) = await m.diz("2")
    assert salvo.startswith("💾 *stall* salvo!")
    assert "1. *stall for time* — enrolar" in salvo
    entrada = m.repo.obter_entrada("stall")
    assert entrada is not None
    assert entrada.status == "praticada"
    assert entrada.sentido.traducao == "travar, emperrar"
    assert [o.traducao for o in entrada.outros_sentidos] == ["enrolar"]
    frases = m.repo.listar_frases("stall")
    assert [f.autor for f in frases] == ["usuario", "bot", "bot", "bot"]
    assert frases[0].veredito == "quase"
    assert m.repo.obter_sessao().estado == Estado.OFFER_EXPANSION

    # 8. Escolhe 1 e 3: viram entradas "nova", e ele decide praticar depois.
    (criadas,) = await m.diz("1,3")
    assert "Criei 2 entradas novas" in criadas
    pendentes = m.repo.listar_entradas("nova")
    assert [e.palavra for e in pendentes] == ["stall for time", "stalled talks"]
    assert all(e.origem == "expansao" and e.pai == "stall" for e in pendentes)
    (encerrado,) = await m.diz("2")
    assert "Manda outra palavra" in encerrado
    assert m.repo.obter_sessao().estado == Estado.IDLE

    # O ciclo consultou a IA com o nível do aluno e sem repetir o que já existia.
    chamadas = dict(m.tutor.chamadas)
    assert chamadas["explain"] == ("stall | the talks stalled", "B1-B2")
    assert chamadas["expansions"][3] == ("stall",)


async def test_pratica_mais_de_uma_frase_e_conclui_direto() -> None:
    tutor = FakeTutor(
        explicacoes=[explicacao_stall()],
        avaliacoes=[avaliacao("incorreta"), avaliacao("correta")],
        expansoes=[expansoes()],
    )
    m = montar(tutor=tutor)
    await m.diz("stall | the talks stalled")
    await m.diz("1")
    await m.diz("I stalled the box.")
    await m.diz("1")  # outra frase
    await m.diz("The negotiations stalled after the first meeting.")
    (resposta,) = await m.diz("3")  # concluir

    assert resposta.startswith("💾 *stall* salvo!")
    assert [f.veredito for f in m.repo.listar_frases("stall")] == ["incorreta", "correta"]


async def test_atalho_frase_direta_no_menu() -> None:
    m = montar(tutor=FakeTutor(explicacoes=[explicacao_stall()], avaliacoes=[avaliacao()]))
    await m.diz("stall")

    (resposta,) = await m.diz("the project stalled last week")

    assert resposta.startswith("⚠️ *Quase lá!*")
    assert m.repo.obter_sessao().estado == Estado.AWAIT_NEXT


async def test_so_salvar_deixa_a_entrada_como_nova_e_oferece_expansoes() -> None:
    m = montar(tutor=FakeTutor(explicacoes=[explicacao_stall()], expansoes=[expansoes()]))
    await m.diz("stall")

    (resposta,) = await m.diz("3")

    assert resposta.startswith("💾 *stall* salvo!")
    entrada = m.repo.obter_entrada("stall")
    assert entrada is not None
    assert entrada.status == "nova"


async def test_pular_expansoes_volta_para_idle() -> None:
    m = montar(tutor=FakeTutor(explicacoes=[explicacao_stall()], expansoes=[expansoes()]))
    await m.diz("stall")
    await m.diz("3")

    (resposta,) = await m.diz("0")

    assert "Manda outra palavra" in resposta
    assert m.repo.obter_sessao().estado == Estado.IDLE
    assert m.repo.listar_entradas("nova")[0].slug == "stall"  # só a própria stall (nova)
    assert len(m.repo.listar_entradas()) == 1


async def test_expansoes_que_o_aluno_ja_tem_nao_duplicam() -> None:
    m = montar(
        tutor=FakeTutor(
            explicacoes=[explicacao_stall(), explicacao_stall()],
            expansoes=[expansoes(), expansoes()],
        )
    )
    await m.diz("stall")
    await m.diz("3")
    await m.diz("1")  # cria "stall for time"
    await m.diz("2")
    await m.diz("stall")  # volta à mesma palavra: mantém a entrada
    await m.diz("3")

    (resposta,) = await m.diz("1")

    assert "Essas você já tinha" in resposta
    assert len(m.repo.listar_entradas()) == 2


async def test_praticar_agora_a_expansao_explica_e_atualiza_a_mesma_entrada() -> None:
    # A IA explica a expressão pela forma base ("stall"); o cartão segue sendo "stall for time".
    expl = explicacao_stall().model_copy(update={"classe": "verbo", "sentido_do_contexto": "s1"})
    tutor = FakeTutor(explicacoes=[explicacao_stall(), expl], expansoes=[expansoes()])
    m = montar(tutor=tutor)
    await m.diz("stall")
    await m.diz("3")
    await m.diz("1")

    (resposta,) = await m.diz("1")  # praticar agora

    assert resposta.startswith("*STALL FOR TIME* (colocação)")
    assert len(m.repo.listar_entradas()) == 2  # não criou uma terceira
    entrada = m.repo.obter_entrada("stall-for-time")
    assert entrada is not None
    assert entrada.sentido.definicao == "to stop making progress"
    assert entrada.origem == "expansao"
    assert entrada.palavra == "stall for time"
    assert m.repo.obter_sessao().entry_id == "stall-for-time"
    assert m.repo.obter_sessao().estado == Estado.AWAIT_CHOICE


# ---- sentido ambíguo -----------------------------------------------------------------------


async def test_sem_contexto_e_varios_sentidos_pergunta_qual() -> None:
    m = montar(tutor=FakeTutor(explicacoes=[explicacao_stall(sentido_do_contexto=None)]))

    (resposta,) = await m.diz("stall")

    assert "mais de um sentido" in resposta
    assert "1️⃣ travar, emperrar — to stop making progress" in resposta
    assert "2️⃣ enrolar — to delay on purpose" in resposta
    assert m.repo.listar_entradas() == []  # nada salvo até escolher
    assert m.repo.obter_sessao().estado == Estado.AWAIT_SENSE


async def test_escolher_o_sentido_cria_a_entrada_e_mostra_o_menu() -> None:
    m = montar(tutor=FakeTutor(explicacoes=[explicacao_stall(sentido_do_contexto=None)]))
    await m.diz("stall")

    (resposta,) = await m.diz("2")

    assert resposta.startswith("*STALL* (verbo) · B2\n🇧🇷 enrolar")
    entrada = m.repo.obter_entrada("stall")
    assert entrada is not None
    assert entrada.sentido.traducao == "enrolar"
    assert m.repo.obter_sessao().estado == Estado.AWAIT_CHOICE
    assert m.repo.obter_sessao().explicacao_pendente is None


async def test_palavra_com_um_unico_sentido_nao_pergunta() -> None:
    expl = explicacao_stall(sentido_do_contexto=None, dois_sentidos=False)
    m = montar(tutor=FakeTutor(explicacoes=[expl]))

    (resposta,) = await m.diz("stall")

    assert "O que você quer fazer?" in resposta


async def test_numero_invalido_reenvia_o_menu_com_lembrete() -> None:
    m = montar(tutor=FakeTutor(explicacoes=[explicacao_stall(sentido_do_contexto=None)]))
    await m.diz("stall")

    (resposta,) = await m.diz("7")

    assert resposta.startswith("Não entendi")
    assert "1️⃣ travar, emperrar" in resposta
    assert m.repo.obter_sessao().estado == Estado.AWAIT_SENSE


# ---- palavra nova no meio do fluxo ---------------------------------------------------------


async def test_palavra_nova_pergunta_e_praticar_agora_salva_a_anterior() -> None:
    nova = explicacao_stall().model_copy(update={"palavra": "hedge", "sentido_do_contexto": "s1"})
    m = montar(tutor=FakeTutor(explicacoes=[explicacao_stall(), nova]))
    await m.diz("stall")

    (pergunta,) = await m.diz("hedge")
    assert "parece uma palavra nova" in pergunta
    assert "Praticar *hedge* agora (salvo a anterior)" in pergunta
    assert m.repo.obter_sessao().estado == Estado.AWAIT_NEW_WORD

    (resposta,) = await m.diz("1")

    assert resposta.startswith("*HEDGE*")
    assert m.repo.obter_entrada("stall") is not None
    assert m.repo.obter_entrada("hedge") is not None
    assert m.repo.obter_sessao().pendente_nova_palavra is None


async def test_palavra_nova_e_era_minha_frase_avalia_a_frase() -> None:
    m = montar(
        tutor=FakeTutor(explicacoes=[explicacao_stall()], avaliacoes=[avaliacao("incorreta")])
    )
    await m.diz("stall")
    await m.diz("hedge")

    (resposta,) = await m.diz("2")

    assert resposta.startswith("❌ *Ainda não.*")
    (chamada,) = [c for c in m.tutor.chamadas if c[0] == "evaluate"]
    assert chamada[1][2] == "hedge"
    assert m.repo.obter_sessao().estado == Estado.AWAIT_NEXT


async def test_palavra_nova_durante_a_escolha_de_sentido_nao_avalia_sem_sentido() -> None:
    m = montar(tutor=FakeTutor(explicacoes=[explicacao_stall(sentido_do_contexto=None)]))
    await m.diz("stall")
    await m.diz("hedge")

    (resposta,) = await m.diz("2")  # "era minha frase" — mas ainda falta o sentido

    assert "Qual sentido de *stall*" in resposta
    assert m.repo.obter_sessao().estado == Estado.AWAIT_SENSE


# ---- modo producao_primeiro ------------------------------------------------------------------


async def test_modo_producao_primeiro_pede_a_frase_direto() -> None:
    tutor = FakeTutor(
        explicacoes=[explicacao_stall()], avaliacoes=[avaliacao()], exemplos=[EXEMPLOS]
    )
    m = montar(modo="producao_primeiro", tutor=tutor)

    (explicacao,) = await m.diz("stall | the talks stalled")

    assert explicacao.endswith(
        "Escreve uma frase com *stall* ✍️\n1️⃣ Me dá um exemplo  ·  2️⃣ Só salvar"
    )
    assert m.repo.obter_sessao().estado == Estado.AWAIT_SENTENCE

    (exemplos,) = await m.diz("1")
    assert exemplos.startswith("📝 *Exemplos de stall*")

    (pedido,) = await m.diz("1")  # escrever
    assert "Escreve uma frase com *stall*" in pedido


# ---- erros, expiração e limites ---------------------------------------------------------------


async def test_falha_da_ia_avisa_e_mantem_a_sessao() -> None:
    tutor = FakeTutor(explicacoes=[explicacao_stall()], avaliacoes=[LLMError("boom")])
    m = montar(tutor=tutor)
    await m.diz("stall")

    (resposta,) = await m.diz("the talks stalled")

    assert "Não consegui falar com a IA" in resposta
    assert m.repo.obter_sessao().estado == Estado.AWAIT_CHOICE
    assert m.repo.listar_frases("stall") == []


async def test_entrada_que_nao_e_ingles_explica_o_motivo_e_volta_para_idle() -> None:
    from app.domain.models import Explanation

    invalida = Explanation(ok=False, motivo_erro="Isso está em português.")
    m = montar(tutor=FakeTutor(explicacoes=[invalida]))

    (resposta,) = await m.diz("obrigado")

    assert "não parece uma palavra ou expressão em inglês" in resposta
    assert "em português" in resposta
    assert m.repo.listar_entradas() == []
    assert m.repo.obter_sessao().estado == Estado.IDLE


async def test_sessao_parada_por_mais_de_3_horas_volta_para_idle() -> None:
    m = montar(tutor=FakeTutor(explicacoes=[explicacao_stall(), explicacao_stall()]))
    await m.diz("stall")
    m.relogio.avancar(timedelta(hours=3, minutes=1))

    (resposta,) = await m.diz("1")  # em AWAIT_CHOICE seria "escrever uma frase"

    assert resposta.startswith("*STALL*")  # tratou "1" como texto novo, em IDLE
    assert m.repo.obter_entrada("stall") is not None  # o que havia continua salvo


async def test_sessao_dentro_das_3_horas_continua() -> None:
    m = montar(tutor=FakeTutor(explicacoes=[explicacao_stall()]))
    await m.diz("stall")
    m.relogio.avancar(timedelta(hours=2, minutes=59))

    (resposta,) = await m.diz("1")

    assert "Manda a sua frase" in resposta


async def test_cada_envio_espera_de_1_a_2_segundos_e_o_digitando_liga_e_desliga() -> None:
    m = montar(tutor=FakeTutor(explicacoes=[explicacao_stall()]))

    await m.diz("stall")

    assert m.esperas == [1.5]
    assert m.channel.digitando == [(CHAT, True), (CHAT, False)]


async def test_nunca_manda_mais_de_3_mensagens_sem_resposta_do_aluno() -> None:
    m = montar()
    for _ in range(5):
        await m.conversa.enviar("oi")

    assert len(m.channel.textos_enviados) == 3

    m.conversa.usuario_falou()
    await m.conversa.enviar("de novo")

    assert len(m.channel.textos_enviados) == 4


async def test_falha_no_digitando_nao_derruba_a_resposta() -> None:
    m = montar(tutor=FakeTutor(explicacoes=[explicacao_stall()]))

    async def quebrado(chat_id: str, on: bool) -> None:
        raise ConnectionError("WAHA fora do ar")

    m.channel.typing = quebrado  # type: ignore[method-assign]

    (resposta,) = await m.diz("stall")

    assert resposta.startswith("*STALL*")


async def test_midia_responde_que_so_entende_texto() -> None:
    m = montar()

    await m.router.midia_nao_suportada()

    assert "só entendo *texto*" in m.channel.textos_enviados[0][1]


@pytest.mark.parametrize("nivel", ["A2-B1", "B2-C1"])
async def test_o_nivel_do_perfil_vai_para_a_ia(nivel: str) -> None:
    m = montar(tutor=FakeTutor(explicacoes=[explicacao_stall()]))
    await m.diz(f"/nivel {nivel}")

    await m.diz("stall")

    assert m.tutor.chamadas[0] == ("explain", ("stall", nivel))


async def test_destino_pode_mudar_por_mensagem() -> None:
    m = montar()

    await m.router.processar("/ajuda", destino="553199998888@c.us")
    await m.router.processar("/ajuda")  # sem destino: continua no último

    assert [chat for chat, _ in m.channel.textos_enviados] == ["553199998888@c.us"] * 2
