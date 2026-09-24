"""M17 (ADR-0020): a revisão em grupo. Cada card marca UM aluno, escolhido por rodízio (professores
e o próprio bot nunca); só a resposta da pessoa marcada vale a nota; as demais recebem feedback sem
mudar o card; se a pessoa marcada não responde a tempo, o card passa ao próximo, uma vez, e depois
a rodada fecha. Sem rede, sem credencial, com o relógio controlado."""

from __future__ import annotations

from datetime import timedelta
from itertools import pairwise
from zoneinfo import ZoneInfo

import httpx
import pytest

from app import messages
from app.domain.models import Entry, Estado, Membro, Profile, Revisao, SentidoSalvo
from app.flows.base import Autor, Participantes
from app.services.fake_llm import FakeTutor
from app.services.lembretes import Agendador
from tests.helpers import ANA, BIA, CAIO, GRUPO, T0, Montagem, montar

BOT = "5531988887777"
CARLA = Autor("5541900000001", "Carla")  # professora
SENTIDO = SentidoSalvo(traducao="travar", definicao="to stop making progress")
NUMEROS = [ANA.numero, BIA.numero, CAIO.numero]


def _bom(feedback: str = "Nice!") -> Revisao:
    return Revisao(tipo="definicao", qualidade="bom", feedback=feedback)


def _de_novo() -> Revisao:
    return Revisao(tipo="frase", qualidade="de_novo", feedback="Not quite.", correcao="It stalled.")


def _palavras(n: int) -> list[Entry]:
    return [
        Entry(
            slug=f"w{i}",
            palavra=f"w{i}",
            classe="verb",
            cefr_estimado="B2",
            sentido=SENTIDO,
            criado_em=T0 - timedelta(days=30 - i),
            atualizado_em=T0 - timedelta(days=30 - i),
            proxima_revisao=T0 - timedelta(days=10 - i),
        )
        for i in range(n)
    ]


def _turma(
    *,
    palavras: int = 3,
    revisoes: int = 8,
    alunos: tuple[Autor, ...] = (ANA, BIA, CAIO),
    participantes: list[str] | None = None,
    limite: int = 5,
    participantes_do_grupo: Participantes | None = None,
) -> Montagem:
    """Uma turma com `alunos` e a professora Carla; o sorteio é determinístico (o primeiro)."""
    m = montar(
        tutor=FakeTutor(revisoes=[_bom() for _ in range(revisoes)]),
        grupo_limite=limite,
        numero_do_bot=BOT,
        sortear=lambda itens: itens[0],
        participantes=participantes_do_grupo,
    )
    m.channel.participantes_de_grupos[GRUPO] = (
        participantes
        if participantes is not None
        else [*(a.numero for a in alunos), CARLA.numero, BOT]
    )
    repo = m.banco.do_espaco(GRUPO)
    for i, aluno in enumerate(alunos):
        repo.salvar_membro(
            aluno.numero, Membro(nome=aluno.nome, entrou_em=T0 + timedelta(minutes=i))
        )
    repo.salvar_membro(CARLA.numero, Membro(papel="professor", nome=CARLA.nome, entrou_em=T0))
    for entrada in _palavras(palavras):
        repo.criar_entrada(entrada)
    return m


def _marcado(m: Montagem) -> str | None:
    return m.banco.do_espaco(GRUPO).obter_sessao().marcado_id


def _ultima_mencao(m: Montagem) -> tuple[str, ...]:
    return m.channel.mencoes_enviadas[-1][1]


# --- começar a revisão ------------------------------------------------------------------------


async def test_review_marca_um_aluno_e_o_card_leva_a_mencao() -> None:
    m = _turma()

    (card,) = await m.diz_no_grupo(ANA, "!review")

    marcado = _marcado(m)
    assert marcado in NUMEROS
    assert _ultima_mencao(m) == (marcado,)
    assert f"@{marcado}, your turn" in card
    assert "Practice time" in card and "1/3" in card
    assert "Anyone can type !0" in card
    assert m.banco.do_espaco(GRUPO).obter_sessao().estado == Estado.REVIEWING


async def test_professor_e_o_proprio_bot_nunca_sao_marcados() -> None:
    m = _turma(alunos=(ANA,), participantes=[ANA.numero, CARLA.numero, BOT])

    for _ in range(3):
        await m.diz_no_grupo(ANA, "!review")
        await m.diz_no_grupo(ANA, "!0")

    marcados = {mencao for _, mencoes in m.channel.mencoes_enviadas for mencao in mencoes}
    assert marcados == {ANA.numero}


async def test_o_limite_por_sessao_do_grupo_e_configuravel() -> None:
    m = _turma(palavras=8, limite=5)

    (card,) = await m.diz_no_grupo(ANA, "!review")

    assert "1/5" in card and "5 words to review" in card


async def test_sem_nenhum_aluno_a_revisao_nao_comeca_e_o_review_avisa() -> None:
    m = _turma(alunos=(), participantes=[CARLA.numero, BOT])

    respostas = await m.diz_no_grupo(CARLA, "!review")

    assert respostas == [messages.grupo_sem_aluno("!")]
    assert m.channel.mencoes_enviadas == []
    assert m.banco.do_espaco(GRUPO).obter_sessao().estado == Estado.IDLE


async def test_o_lembrete_sem_aluno_elegivel_fica_em_silencio() -> None:
    m = _turma(alunos=(), participantes=[CARLA.numero, BOT])
    _dar_lembrete(m)

    await _agendador(m)._tick()

    assert m.channel.textos_enviados == []


async def test_participantes_do_grupo_atualizam_o_cadastro_e_quem_saiu_nao_e_marcado() -> None:
    novato = "5561955550000"
    m = _turma(alunos=(ANA, BIA), participantes=[ANA.numero, novato, CARLA.numero, BOT])
    # a Bia saiu do grupo; o Novato nunca escreveu com prefixo

    marcados: set[str] = set()
    for _ in range(4):
        await m.diz_no_grupo(ANA, "!review")
        marcados.add(_marcado(m) or "")
        await m.diz_no_grupo(ANA, "!0")

    assert marcados == {ANA.numero, novato}  # Bia (fora do grupo) nunca
    cadastro = m.banco.do_espaco(GRUPO).obter_membro(novato)
    assert cadastro is not None and cadastro.papel == "aluno"


async def test_se_a_lista_de_participantes_falha_usa_o_cadastro_de_membros() -> None:
    async def quebra(_: str) -> list[str]:
        raise httpx.ConnectError("WAHA fora do ar")

    m = _turma(participantes_do_grupo=quebra)

    await m.diz_no_grupo(ANA, "!review")

    assert _marcado(m) in NUMEROS


# --- responder --------------------------------------------------------------------------------


async def test_a_resposta_da_pessoa_marcada_vale_a_nota_e_o_proximo_card_marca_outro_aluno() -> (
    None
):
    m = _turma()
    await m.diz_no_grupo(ANA, "!review")
    primeiro = _marcado(m)
    autor = next(a for a in (ANA, BIA, CAIO) if a.numero == primeiro)
    entrada_antes = m.banco.do_espaco(GRUPO).obter_entrada("w0")
    assert entrada_antes is not None

    (resposta,) = await m.diz_no_grupo(autor, "!it means to stop making progress")

    assert "Nice!" in resposta and "2/3" in resposta  # feedback + próximo card, numa mensagem só
    segundo = _marcado(m)
    assert segundo != primeiro and segundo in NUMEROS  # ninguém duas vezes seguidas
    assert _ultima_mencao(m) == (segundo,)
    depois = m.banco.do_espaco(GRUPO).obter_entrada(entrada_antes.slug)
    assert depois is not None and depois.proxima_revisao != entrada_antes.proxima_revisao
    (r,) = m.banco.do_espaco(GRUPO).listar_respostas()
    assert (r.autor_id, r.marcado, r.qualidade) == (primeiro, True, "bom")


async def test_a_resposta_de_quem_nao_e_o_marcado_da_feedback_mas_nao_muda_nota_nem_card() -> None:
    m = _turma()
    await m.diz_no_grupo(ANA, "!review")
    primeiro = _marcado(m)
    intruso = next(a for a in (ANA, BIA, CAIO) if a.numero != primeiro)
    antes = m.banco.do_espaco(GRUPO).obter_entrada("w0")
    sessao_antes = m.banco.do_espaco(GRUPO).obter_sessao()
    mencoes_antes = len(m.channel.mencoes_enviadas)

    (resposta,) = await m.diz_no_grupo(intruso, "!maybe it means to delay")

    assert "doesn't count" in resposta and "Nice!" in resposta  # feedback
    assert "2/3" not in resposta  # o card não avançou
    assert len(m.channel.mencoes_enviadas) == mencoes_antes  # ninguém foi marcado de novo
    depois = m.banco.do_espaco(GRUPO).obter_entrada("w0")
    assert depois is not None and antes is not None
    assert depois.proxima_revisao == antes.proxima_revisao and depois.repeticoes == antes.repeticoes
    sessao = m.banco.do_espaco(GRUPO).obter_sessao()
    assert (sessao.marcado_id, sessao.revisao_atual, sessao.marcacao_expira_em) == (
        sessao_antes.marcado_id,
        sessao_antes.revisao_atual,
        sessao_antes.marcacao_expira_em,
    )
    (r,) = m.banco.do_espaco(GRUPO).listar_respostas()
    assert (r.autor_id, r.marcado) == (intruso.numero, False)


async def test_a_professora_pode_comentar_mas_a_resposta_dela_nao_conta() -> None:
    m = _turma()
    await m.diz_no_grupo(ANA, "!review")
    marcado = _marcado(m)

    (resposta,) = await m.diz_no_grupo(CARLA, "!it means to stop")

    assert "doesn't count" in resposta
    assert _marcado(m) == marcado


async def test_a_frase_de_quem_nao_e_o_marcado_tambem_fica_com_o_autor() -> None:
    tutor = FakeTutor(revisoes=[Revisao(tipo="frase", qualidade="bom", feedback="Good.")])
    m = _turma()
    m.tutor.revisoes[:] = tutor.revisoes
    await m.diz_no_grupo(ANA, "!review")
    intruso = next(a for a in (ANA, BIA, CAIO) if a.numero != _marcado(m))

    await m.diz_no_grupo(intruso, "!The project stalled again.")

    frases = [f for f in m.banco.do_espaco(GRUPO).listar_frases("w0") if f.autor == "usuario"]
    assert [f.autor_id for f in frases] == [intruso.numero]


async def test_a_rotacao_distribui_os_cards_e_nunca_repete_o_marcado_seguido() -> None:
    m = _turma(palavras=5, revisoes=10)
    await m.diz_no_grupo(ANA, "!review")

    sequencia = [_marcado(m)]
    for _ in range(4):
        autor = next(a for a in (ANA, BIA, CAIO) if a.numero == _marcado(m))
        await m.diz_no_grupo(autor, "!answer")
        sequencia.append(_marcado(m))

    assert sequencia[-1] is None or sequencia[-1] in NUMEROS
    marcados = [n for n in sequencia[:5] if n]
    assert all(a != b for a, b in pairwise(marcados))
    assert set(marcados) == set(NUMEROS)  # os três alunos foram marcados


async def test_zero_ou_stop_de_qualquer_participante_fecha_com_o_resumo() -> None:
    for saida in ("!0", "!stop"):
        m = _turma()
        await m.diz_no_grupo(ANA, "!review")

        (resposta,) = await m.diz_no_grupo(CARLA, saida)  # até a professora pode sair

        assert "Practice done" in resposta or "No pending reviews" in resposta
        assert m.banco.do_espaco(GRUPO).obter_sessao().estado == Estado.IDLE
        assert m.banco.do_espaco(GRUPO).obter_sessao().marcado_id is None


async def test_o_ultimo_card_fecha_a_rodada_com_o_resumo() -> None:
    m = _turma(palavras=1, revisoes=2)
    await m.diz_no_grupo(ANA, "!review")
    autor = next(a for a in (ANA, BIA, CAIO) if a.numero == _marcado(m))

    (resposta,) = await m.diz_no_grupo(autor, "!it means to stop")

    assert "Practice done" in resposta
    assert m.banco.do_espaco(GRUPO).obter_sessao().estado == Estado.IDLE


async def test_na_revisao_so_stop_e_help_escapam_da_resposta() -> None:
    m = _turma()
    await m.diz_no_grupo(ANA, "!review")

    (ajuda,) = await m.diz_no_grupo(BIA, "!help")
    (resposta,) = await m.diz_no_grupo(BIA, "!list")  # é uma resposta, não o comando

    assert ajuda == messages.ajuda_do_grupo("!")
    assert "doesn't count" in resposta or "Nice!" in resposta
    assert m.banco.do_espaco(GRUPO).obter_sessao().estado == Estado.REVIEWING


async def test_o_group_conta_as_respostas_de_revisao_de_cada_um() -> None:
    m = _turma()
    await m.diz_no_grupo(ANA, "!review")
    autor = next(a for a in (ANA, BIA, CAIO) if a.numero == _marcado(m))
    await m.diz_no_grupo(autor, "!answer")
    await m.diz_no_grupo(CARLA, "!0")  # durante a revisão, `!group` seria uma resposta

    (perfil,) = await m.diz_no_grupo(CARLA, "!group")

    assert f"• {autor.nome} (student) · 1 review answers" in perfil


# --- o privado não mudou ----------------------------------------------------------------------


async def test_a_revisao_no_privado_segue_sem_marcacao() -> None:
    m = montar(tutor=FakeTutor(revisoes=[_bom()]))
    for e in _palavras(2):
        m.repo.criar_entrada(e)

    (card,) = await m.diz("/review")

    assert "@" not in card and "Type 0 to leave the practice" in card
    assert m.channel.mencoes_enviadas == []
    assert m.repo.obter_sessao().marcado_id is None


# --- timeout ----------------------------------------------------------------------------------


def _agendador(m: Montagem) -> Agendador:
    async def dormir(_: float) -> None:
        return None

    return Agendador(
        router=m.router, banco=m.banco, agora=m.relogio.agora, fuso=ZoneInfo("UTC"), dormir=dormir
    )


def _dar_lembrete(m: Montagem) -> None:
    m.banco.do_espaco(GRUPO).salvar_perfil(
        Profile(nivel="B1-B2", chat_id=GRUPO, lembretes_por_dia=3, proximo_lembrete=T0)
    )
    m.relogio.avancar(timedelta(seconds=1))


async def test_o_lembrete_do_grupo_marca_um_aluno() -> None:
    m = _turma()
    _dar_lembrete(m)

    await _agendador(m)._tick()

    ((chat, texto),) = m.channel.textos_enviados
    assert chat == GRUPO and "Practice time" in texto and "your turn" in texto
    assert _marcado(m) in NUMEROS and _ultima_mencao(m) == (_marcado(m),)


async def test_sem_resposta_em_3_horas_o_card_passa_ao_proximo_aluno_uma_vez() -> None:
    m = _turma()
    await m.diz_no_grupo(ANA, "!review")
    primeiro = _marcado(m)

    m.relogio.avancar(timedelta(hours=2, minutes=59))
    await _agendador(m)._tick()
    assert _marcado(m) == primeiro  # ainda dentro do prazo

    m.relogio.avancar(timedelta(minutes=2))
    await _agendador(m)._tick()

    segundo = _marcado(m)
    assert segundo != primeiro and segundo in NUMEROS
    texto = m.channel.textos_enviados[-1][1]
    assert "passing this one on" in texto and f"@{segundo}" in texto
    assert _ultima_mencao(m) == (segundo,)
    sessao = m.banco.do_espaco(GRUPO).obter_sessao()
    assert sessao.marcacao_tentativas == 1 and sessao.revisao_atual == "w0"  # o MESMO card
    assert sessao.estado == Estado.REVIEWING


async def test_o_segundo_silencio_fecha_a_rodada_com_o_resumo() -> None:
    m = _turma()
    await m.diz_no_grupo(ANA, "!review")
    m.relogio.avancar(timedelta(hours=3, minutes=1))
    await _agendador(m)._tick()  # repassa

    m.relogio.avancar(timedelta(hours=3, minutes=1))
    await _agendador(m)._tick()  # ninguém respondeu de novo

    assert "Nobody answered in time" in m.channel.textos_enviados[-1][1]
    sessao = m.banco.do_espaco(GRUPO).obter_sessao()
    assert sessao.estado == Estado.IDLE and sessao.marcado_id is None


async def test_o_timeout_respeita_o_limite_de_tres_mensagens_seguidas() -> None:
    m = _turma()
    await m.diz_no_grupo(ANA, "!review")  # 1: o card (o bot tomou a iniciativa)
    m.relogio.avancar(timedelta(hours=3, minutes=1))
    await _agendador(m)._tick()  # 2: o repasse
    m.relogio.avancar(timedelta(hours=3, minutes=1))
    await _agendador(m)._tick()  # 3: o fechamento

    assert len(m.channel.textos_enviados) == 3
    m.relogio.avancar(timedelta(hours=3, minutes=1))
    await _agendador(m)._tick()  # nada mais a fazer: a sessão já fechou
    assert len(m.channel.textos_enviados) == 3


async def test_quem_responde_a_tempo_zera_o_prazo_do_card_seguinte() -> None:
    m = _turma()
    await m.diz_no_grupo(ANA, "!review")
    m.relogio.avancar(timedelta(hours=2))
    autor = next(a for a in (ANA, BIA, CAIO) if a.numero == _marcado(m))
    await m.diz_no_grupo(autor, "!answer")  # 2h depois do início: novo card, novo prazo
    segundo = _marcado(m)

    m.relogio.avancar(timedelta(hours=2))  # 4h desde o início, 2h do novo card
    await _agendador(m)._tick()

    assert _marcado(m) == segundo
    assert m.banco.do_espaco(GRUPO).obter_sessao().marcacao_tentativas == 0


async def test_com_um_unico_aluno_o_repasse_marca_ele_de_novo_e_depois_fecha() -> None:
    m = _turma(alunos=(ANA,), participantes=[ANA.numero, BOT])
    await m.diz_no_grupo(ANA, "!review")
    m.relogio.avancar(timedelta(hours=3, minutes=1))

    await _agendador(m)._tick()

    assert _marcado(m) == ANA.numero
    m.relogio.avancar(timedelta(hours=3, minutes=1))
    await _agendador(m)._tick()
    assert m.banco.do_espaco(GRUPO).obter_sessao().estado == Estado.IDLE


async def test_uma_falha_ao_expirar_um_grupo_nao_impede_o_agendador(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    m = _turma()
    await m.diz_no_grupo(ANA, "!review")
    m.relogio.avancar(timedelta(hours=3, minutes=1))

    async def quebra(_: str, forcar: bool = False) -> None:
        raise RuntimeError("falha só aqui")

    monkeypatch.setattr(m.router, "expirar_marcacao", quebra)

    await _agendador(m)._tick()  # não levanta


@pytest.mark.parametrize("estado", [Estado.IDLE, Estado.AWAIT_ACTION])
async def test_timeout_de_um_grupo_sem_revisao_em_andamento_nao_faz_nada(estado: Estado) -> None:
    m = _turma()
    await m.router.expirar_marcacao(GRUPO)

    assert m.channel.textos_enviados == []
    assert m.banco.do_espaco(GRUPO).obter_sessao().estado == Estado.IDLE


async def test_lista_vazia_de_participantes_e_tratada_como_falha_e_usa_o_cadastro() -> None:
    m = _turma(participantes=[])

    await m.diz_no_grupo(ANA, "!review")

    assert _marcado(m) in NUMEROS


async def test_o_fechamento_da_rodada_no_grupo_so_cita_comandos_do_grupo() -> None:
    m = _turma(palavras=1, revisoes=2)
    await m.diz_no_grupo(ANA, "!review")
    autor = next(a for a in (ANA, BIA, CAIO) if a.numero == _marcado(m))

    (fim,) = await m.diz_no_grupo(autor, "!it means to stop")

    assert "Add a new word whenever you want: !add word." in fim
    assert "Send me" not in fim
