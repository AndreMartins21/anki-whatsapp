"""Prática com letra de música (M13, seção 5.8) de ponta a ponta: /song → escolha entre
homônimas → verso a verso → resumo → salvar. Todas as músicas e letras aqui são inventadas
(ADR-0016: nunca letra real em teste)."""

from __future__ import annotations

from app.domain.models import CompreensaoDoVerso, Estado, Explanation, LinhaDaMusica, Sense
from app.domain.musica import Musica
from app.services.fake_llm import FakeTutor
from app.services.letras import FakeLyrics
from app.services.llm import LLMError
from tests.helpers import Montagem, montar

LETRA = """[Verse 1]
I left my keys beside the kitchen door
The morning bus is running late once more

[Chorus]
Hold on, the city never sleeps
Hold on, the city never sleeps
"""
LETRA_PT = """Deixei a chave na porta da cozinha
O ônibus da manhã atrasou de novo
Segura firme que a cidade não dorme
"""

PAPER_PLANE = Musica(1, "Paper Plane", "The Inventors", LETRA)
PAPER_PLANE_COVER = Musica(2, "Paper Plane", "Someone Else", LETRA)
AVIAO_DE_PAPEL = Musica(3, "Aviao de Papel", "Os Inventores", LETRA_PT)
PAPER_PLANE_PT = Musica(4, "Paper Plane", "Os Inventores", LETRA_PT)


def _linha(
    compreensao: CompreensaoDoVerso = "entendeu", expressoes: list[str] | None = None
) -> LinhaDaMusica:
    return LinhaDaMusica(
        compreensao=compreensao,
        feedback="Nice try!",
        significado="" if compreensao == "entendeu" else "Wait, the city is always awake.",
        expressoes=expressoes or [],
    )


def _explicacao(palavra: str, traducao: str) -> Explanation:
    return Explanation(
        ok=True,
        palavra=palavra,
        classe="phrasal verb",
        cefr_estimado="B1",
        sentidos=[
            Sense(
                id="s1",
                traducao=traducao,
                definicao=f"meaning of {palavra}",
                exemplo=f"Please [[{palavra}]] a second.",
            )
        ],
        sentido_do_contexto="s1",
        frase_contexto=f"[[{palavra}]], the city never sleeps",
    )


def _montar(*musicas: Musica, tutor: FakeTutor | None = None, falhar: bool = False) -> Montagem:
    return montar(tutor=tutor, letras=FakeLyrics(list(musicas), falhar=falhar))


async def test_sem_argumento_mostra_como_usar() -> None:
    m = _montar(PAPER_PLANE)
    (resposta,) = await m.diz("/song")
    assert "/song paper plane" in resposta
    assert m.repo.obter_sessao().estado == Estado.IDLE


async def test_uma_musica_so_comeca_direto_pelo_primeiro_verso() -> None:
    m = _montar(PAPER_PLANE, AVIAO_DE_PAPEL)

    (resposta,) = await m.diz("/song paper plane")

    assert "*Paper Plane* — The Inventors" in resposta
    assert "3 lines" in resposta  # o refrão repetido e a marcação [Chorus] saem
    assert "Line 1/3" in resposta
    assert "_I left my keys beside the kitchen door_" in resposta
    assert "Type 0 to leave the practice" in resposta
    sessao = m.repo.obter_sessao()
    assert sessao.estado == Estado.SONG_PRACTICE
    assert sessao.musica_indice == 0


async def test_homonimas_pedem_confirmacao_e_o_numero_escolhe() -> None:
    m = _montar(PAPER_PLANE, PAPER_PLANE_COVER)

    (lista,) = await m.diz("/song paper plane")
    assert "1. *Paper Plane* — The Inventors" in lista
    assert "2. *Paper Plane* — Someone Else" in lista
    assert m.repo.obter_sessao().estado == Estado.SONG_PICKING

    (invalida,) = await m.diz("7")
    assert "Pick one of the numbers" in invalida
    assert m.repo.obter_sessao().estado == Estado.SONG_PICKING

    (inicio,) = await m.diz("2")
    assert "*Paper Plane* — Someone Else" in inicio
    assert m.repo.obter_sessao().estado == Estado.SONG_PRACTICE


async def test_zero_cancela_a_escolha() -> None:
    m = _montar(PAPER_PLANE, PAPER_PLANE_COVER)
    await m.diz("/song paper plane")
    (resposta,) = await m.diz("0")
    assert "No problem" in resposta
    assert m.repo.obter_sessao().estado == Estado.IDLE


async def test_texto_na_escolha_e_uma_nova_busca_com_artista() -> None:
    letras = FakeLyrics([PAPER_PLANE, PAPER_PLANE_COVER])
    m = montar(letras=letras)
    await m.diz("/song paper plane")

    (inicio,) = await m.diz("paper plane - someone")

    assert letras.buscas[-1] == ("paper plane", "someone")
    assert "Someone Else" in inicio


async def test_letra_em_outro_idioma_pede_outra_musica() -> None:
    m = _montar(PAPER_PLANE_PT)
    (resposta,) = await m.diz("/song paper plane")
    assert "aren't in English" in resposta
    assert m.repo.obter_sessao().estado == Estado.IDLE


async def test_versao_em_outro_idioma_nao_entra_na_lista() -> None:
    m = _montar(PAPER_PLANE, PAPER_PLANE_PT)
    (resposta,) = await m.diz("/song paper plane")
    assert "Os Inventores" not in resposta
    assert m.repo.obter_sessao().estado == Estado.SONG_PRACTICE  # sobrou uma só: começa direto


async def test_nao_encontrada() -> None:
    m = _montar(PAPER_PLANE)
    (resposta,) = await m.diz("/song nothing like this")
    assert "couldn't find *nothing like this*" in resposta


async def test_fonte_fora_do_ar() -> None:
    m = _montar(PAPER_PLANE, falhar=True)
    (resposta,) = await m.diz("/song paper plane")
    assert "couldn't reach the lyrics library" in resposta


async def test_ciclo_completo_ate_salvar_as_expressoes() -> None:
    tutor = FakeTutor(
        linhas_de_musica=[
            _linha("entendeu"),
            _linha("parcial", ["running late", "not in the line"]),
            _linha("nao_entendeu", ["Hold on", "never sleeps"]),
        ],
        explicacoes=[
            _explicacao("hold on", "espera aí"),
            _explicacao("run late", "estar atrasado"),
        ],
    )
    m = _montar(PAPER_PLANE, tutor=tutor)
    await m.diz("/song paper plane")

    (turno1,) = await m.diz("ele deixou as chaves perto da porta")
    assert turno1.startswith("✅ Nice try!")
    assert "Line 2/3" in turno1
    assert tutor.chamadas[-1] == (
        "song_line",
        (
            "Paper Plane",
            "I left my keys beside the kitchen door",
            "ele deixou as chaves perto da porta",
            "B1-B2",
        ),
    )

    (turno2,) = await m.diz("the bus is late")
    assert turno2.startswith("🤔 Nice try!")
    assert "💬 Wait" in turno2
    assert "Line 3/3" in turno2

    (resumo,) = await m.diz("no idea")
    assert "you went through 3 of 3 lines" in resumo
    # só as expressões que estão no verso, na ordem em que apareceram
    assert "1. running late\n2. Hold on\n3. never sleeps" in resumo
    assert "not in the line" not in resumo
    assert m.repo.obter_sessao().estado == Estado.SONG_SAVING

    (salvas,) = await m.diz("2 and 1")

    assert "Saved to your dictionary" in salvas
    palavras = {e.palavra for e in m.repo.listar_entradas()}
    assert palavras == {"hold on", "run late"}
    explicadas = sorted(str(args[0]) for nome, args in tutor.chamadas if nome == "explain")
    assert explicadas == [
        "Hold on | Hold on, the city never sleeps",
        "running late | The morning bus is running late once more",
    ]
    assert m.repo.obter_sessao().estado == Estado.IDLE


async def test_zero_no_meio_fecha_com_o_que_ja_foi_feito() -> None:
    tutor = FakeTutor(linhas_de_musica=[_linha("parcial", ["kitchen door"])])
    m = _montar(PAPER_PLANE, tutor=tutor)
    await m.diz("/song paper plane")
    await m.diz("chaves na porta")

    (resumo,) = await m.diz("0")

    assert "you went through 1 of 3 lines" in resumo
    assert "1. kitchen door" in resumo
    (descartado,) = await m.diz("0")
    assert "nothing saved" in descartado
    assert m.repo.listar_entradas() == []
    assert m.repo.obter_sessao().estado == Estado.IDLE


async def test_sem_expressoes_o_resumo_nao_oferece_salvar() -> None:
    m = _montar(PAPER_PLANE)
    await m.diz("/song paper plane")
    (resumo,) = await m.diz("stop")
    assert "0 of 3" in resumo
    assert "save" not in resumo
    assert m.repo.obter_sessao().estado == Estado.IDLE


async def test_cancel_durante_a_pratica_e_igual_ao_zero() -> None:
    m = _montar(PAPER_PLANE)
    await m.diz("/song paper plane")
    (resumo,) = await m.diz("/cancel")
    assert "you went through 0 of 3 lines" in resumo


async def test_all_salva_todas_e_numero_invalido_pergunta_de_novo() -> None:
    tutor = FakeTutor(
        linhas_de_musica=[_linha("parcial", ["kitchen door"])],
        explicacoes=[_explicacao("kitchen door", "porta da cozinha")],
    )
    m = _montar(PAPER_PLANE, tutor=tutor)
    await m.diz("/song paper plane")
    await m.diz("?")
    await m.diz("0")

    (invalida,) = await m.diz("5")
    assert "Pick numbers from the list" in invalida
    assert m.repo.obter_sessao().estado == Estado.SONG_SAVING

    await m.diz("all")
    assert [e.palavra for e in m.repo.listar_entradas()] == ["kitchen door"]


async def test_palavra_nova_na_oferta_segue_para_a_explicacao() -> None:
    tutor = FakeTutor(
        linhas_de_musica=[_linha("parcial", ["kitchen door"])],
        explicacoes=[_explicacao("hedge", "cercar")],
    )
    m = _montar(PAPER_PLANE, tutor=tutor)
    await m.diz("/song paper plane")
    await m.diz("?")
    await m.diz("0")

    await m.diz("hedge")

    assert tutor.chamadas[-1] == ("explain", ("hedge", "B1-B2"))
    assert m.repo.obter_sessao().estado == Estado.AWAIT_ACTION


async def test_falha_da_ia_mantem_o_verso_atual() -> None:
    tutor = FakeTutor(linhas_de_musica=[LLMError("fora do ar"), _linha("entendeu")])
    m = _montar(PAPER_PLANE, tutor=tutor)
    await m.diz("/song paper plane")

    (erro,) = await m.diz("chaves")
    assert "couldn't reach the AI" in erro
    assert m.repo.obter_sessao().musica_indice == 0

    (turno,) = await m.diz("chaves")
    assert "Line 2/3" in turno


async def test_sem_fonte_de_letras_configurada() -> None:
    m = montar()
    (resposta,) = await m.diz("/song paper plane")
    assert "isn't available" in resposta


async def test_help_lista_o_song() -> None:
    m = _montar(PAPER_PLANE)
    (ajuda,) = await m.diz("/help")
    assert "/song" in ajuda
