"""Pronúncia em áudio (M23, ADR-0024): opção 1 do menu e /listen mandam duas notas de voz —
o termo e a frase de exemplo —, sempre sob demanda, com o áudio vindo do cache depois da 1ª vez."""

from __future__ import annotations

from app.domain.models import Entry, Estado, SentidoSalvo
from app.services.audio import ServicoAudio
from app.services.fake_llm import FakeTutor
from app.services.fake_tts import FakeSintetizador
from app.services.storage import CacheAudioEmMemoria
from tests.helpers import CHAT, GRUPO, T0, Montagem, expansoes, explicacao_stall, montar

VOZ = "en-US-Neural2-F"


def _com_audio(
    *, sintetizador: FakeSintetizador | None = None
) -> tuple[Montagem, FakeSintetizador, CacheAudioEmMemoria]:
    sintetizador = sintetizador or FakeSintetizador()
    cache = CacheAudioEmMemoria()
    m = montar(
        tutor=FakeTutor(explicacoes=[explicacao_stall()], expansoes=[expansoes()]),
        audio=ServicoAudio(sintetizador, cache, VOZ),
    )
    return m, sintetizador, cache


async def test_opcao_1_manda_o_termo_e_a_frase_de_exemplo_em_duas_notas_de_voz() -> None:
    m, sintetizador, _ = _com_audio()
    await m.diz("stall | the talks stalled")

    textos = await m.diz("1")

    assert textos == ['🔊 *stall*\n"The talks stalled."']
    assert m.channel.vozes_enviadas == [(CHAT, b"ogg:stall"), (CHAT, b"ogg:The talks stalled.")]
    assert sintetizador.chamadas == [("stall", VOZ), ("The talks stalled.", VOZ)]


async def test_a_conversa_continua_na_mesma_palavra_depois_do_audio() -> None:
    m, _, _ = _com_audio()
    await m.diz("stall | the talks stalled")

    await m.diz("1")

    sessao = m.repo.obter_sessao()
    assert sessao.estado == Estado.AWAIT_ACTION and sessao.entry_id == "stall"
    (fim,) = await m.diz("4")
    assert fim.startswith("✅")  # "Just save" segue funcionando


async def test_pedir_de_novo_vem_do_cache_sem_sintetizar() -> None:
    m, sintetizador, _ = _com_audio()
    await m.diz("stall | the talks stalled")
    await m.diz("1")

    await m.diz("1")

    assert len(sintetizador.chamadas) == 2  # só a 1ª vez sintetizou
    assert len(m.channel.vozes_enviadas) == 4


async def test_o_link_dos_audios_fica_na_entrada() -> None:
    m, _, cache = _com_audio()
    await m.diz("stall | the talks stalled")

    await m.diz("1")

    entrada = m.repo.obter_entrada("stall")
    assert entrada is not None
    assert entrada.audio_palavra in {f"memoria://{n}" for n in cache.arquivos}
    assert entrada.audio_exemplo in {f"memoria://{n}" for n in cache.arquivos}
    assert entrada.audio_palavra != entrada.audio_exemplo


async def test_falha_do_tts_avisa_sem_derrubar_a_conversa() -> None:
    m, _, _ = _com_audio(sintetizador=FakeSintetizador(falha=True))
    await m.diz("stall | the talks stalled")

    textos = await m.diz("1")

    assert textos == ["🔊 I couldn't make the audio right now. Try again in a bit?"]
    assert m.channel.vozes_enviadas == []
    assert m.repo.obter_sessao().estado == Estado.AWAIT_ACTION


async def test_falha_ao_enviar_a_voz_avisa_sem_derrubar_a_conversa() -> None:
    m, _, _ = _com_audio()
    await m.diz("stall | the talks stalled")
    m.channel.falha_na_voz = True

    textos = await m.diz("1")

    assert textos[-1] == "🔊 I couldn't make the audio right now. Try again in a bit?"
    assert m.repo.obter_sessao().estado == Estado.AWAIT_ACTION


async def test_sem_servico_de_audio_a_opcao_1_avisa() -> None:
    m = montar(tutor=FakeTutor(explicacoes=[explicacao_stall()]))
    await m.diz("stall | the talks stalled")

    textos = await m.diz("1")

    assert textos == ["🔊 I couldn't make the audio right now. Try again in a bit?"]


async def test_no_grupo_a_opcao_1_e_com_o_prefixo() -> None:
    from tests.helpers import ANA

    m, _, _ = _com_audio()
    await m.diz_no_grupo(ANA, "!add stall | the talks stalled")

    textos = await m.diz_no_grupo(ANA, "!1")

    assert textos == ['🔊 *stall*\n"The talks stalled."']
    assert [c for c, _ in m.channel.vozes_enviadas] == [GRUPO, GRUPO]


# ---- /listen ----------------------------------------------------------------------------------


async def test_listen_toca_uma_palavra_ja_salva() -> None:
    m, sintetizador, _ = _com_audio()
    await m.diz("stall | the talks stalled")
    await m.diz("4")  # salva e fecha o card

    textos = await m.diz("/listen stall")

    assert textos == ['🔊 *stall*\n"The talks stalled."']
    assert len(m.channel.vozes_enviadas) == 2
    assert len(sintetizador.chamadas) == 2


async def test_listen_aceita_o_numero_da_lista() -> None:
    m, _, _ = _com_audio()
    await m.diz("stall | the talks stalled")
    await m.diz("4")

    await m.diz("/listen 1")

    assert m.channel.vozes_enviadas[0] == (CHAT, b"ogg:stall")


async def test_listen_sem_palavra_explica_o_uso() -> None:
    m, _, _ = _com_audio()

    (texto,) = await m.diz("/listen")

    assert texto == "Tell me which word: /listen 3 (the number from /list) or /listen stall."
    assert m.channel.vozes_enviadas == []


async def test_listen_de_palavra_que_nao_existe() -> None:
    m, _, _ = _com_audio()

    (texto,) = await m.diz("/listen zebra")

    assert texto.startswith('I couldn\'t find "zebra"')


async def test_entrada_sem_frase_do_bot_manda_so_o_termo() -> None:
    m, _, _ = _com_audio()
    m.repo.criar_entrada(
        Entry(
            slug="hang-on",
            palavra="hang on",
            classe="phrasal verb",
            cefr_estimado="B1",
            sentido=SentidoSalvo(traducao="esperar", definicao="to wait"),
            criado_em=T0,
            atualizado_em=T0,
        )
    )

    textos = await m.diz("/listen hang on")

    assert textos == ["🔊 *hang on*"]
    assert m.channel.vozes_enviadas == [(CHAT, b"ogg:hang on")]
