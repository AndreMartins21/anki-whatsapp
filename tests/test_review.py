"""Testes do fluxo de revisão espaçada (M10, seção 5.7): `montar_fila` (pura) e o ciclo via
`/revisar` com o `Router` + `FakeTutor`."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.domain.models import Entry, Estado, Revisao, SentidoSalvo
from app.flows.review import montar_fila
from app.services.fake_llm import FakeTutor
from tests.helpers import T0, Montagem, montar

SENTIDO = SentidoSalvo(traducao="travar", definicao="to stop making progress")


def _entrada(slug: str, *, criado_em: datetime = T0, **campos: object) -> Entry:
    base = {
        "slug": slug,
        "palavra": slug,
        "classe": "verb",
        "cefr_estimado": "B2",
        "sentido": SENTIDO,
        "criado_em": criado_em,
        "atualizado_em": criado_em,
    }
    return Entry.model_validate(base | campos)


# ---- montar_fila (pura) -----------------------------------------------------------------------


def test_montar_fila_vazia_sem_entradas() -> None:
    assert montar_fila([], T0) == []


def test_montar_fila_vencidas_primeiro_mais_antiga_primeiro() -> None:
    recente = _entrada(
        "b", criado_em=T0 + timedelta(minutes=5), proxima_revisao=T0 - timedelta(days=1)
    )
    antiga = _entrada("a", criado_em=T0, proxima_revisao=T0 - timedelta(days=5))
    nunca_revisada = _entrada("c", criado_em=T0 + timedelta(minutes=1))  # proxima_revisao=None

    fila = montar_fila([recente, antiga, nunca_revisada], T0)

    # Ordenado pela data de vencimento: "a" venceu há mais tempo, "c" nunca foi revisada
    # (criado_em vira o critério) mas seu criado_em é mais recente que a data de vencimento de "b".
    assert fila == ["a", "b", "c"]


def test_montar_fila_completa_ate_o_limite_com_as_que_vencem_mais_cedo() -> None:
    vencida = _entrada("v", proxima_revisao=T0 - timedelta(days=1))
    cedo = _entrada("cedo", criado_em=T0, proxima_revisao=T0 + timedelta(days=1))
    tarde = _entrada("tarde", criado_em=T0, proxima_revisao=T0 + timedelta(days=10))

    fila = montar_fila([tarde, cedo, vencida], T0, limite=2)

    assert fila == ["v", "cedo"]


def test_montar_fila_so_as_vencidas_quando_ja_bate_o_limite() -> None:
    entradas = [_entrada(f"e{i}", proxima_revisao=T0 - timedelta(days=i)) for i in range(3)]

    fila = montar_fila(entradas, T0, limite=2)

    assert len(fila) == 2


# ---- ciclo via /revisar -----------------------------------------------------------------------


async def _com_stall_e_hedge_vencidas() -> Montagem:
    m = montar(tutor=FakeTutor())
    m.repo.criar_entrada(_entrada("stall", criado_em=T0))
    m.repo.criar_entrada(_entrada("hedge", criado_em=T0 + timedelta(minutes=1)))
    return m


async def test_revisar_sem_nada_pendente() -> None:
    m = montar()

    (resposta,) = await m.diz("/revisar")

    assert "No pending reviews" in resposta


async def test_ciclo_completo_de_revisao() -> None:
    m = await _com_stall_e_hedge_vencidas()

    (primeira,) = await m.diz("/revisar")
    assert primeira == (
        "⏰ *Practice time* — 2 words to review.\n\n"
        "🔁 1/2 · *stall*\n"
        "Explain it in English in your own words, or write a sentence using it.\n"
        "_Type 0 to leave the practice._"
    )
    assert m.repo.obter_sessao().estado == Estado.REVIEWING
    assert m.repo.obter_sessao().revisao_atual == "stall"

    m.tutor.revisoes.append(
        Revisao(tipo="definicao", qualidade="bom", feedback="That's exactly right.")
    )
    (segunda,) = await m.diz("to stop making progress")
    assert segunda == (
        "✅ That's exactly right.\n\n"
        "🔁 2/2 · *hedge*\n"
        "Explain it in English in your own words, or write a sentence using it.\n"
        "_Type 0 to leave the practice._"
    )
    entrada_stall = m.repo.obter_entrada("stall")
    assert entrada_stall is not None
    assert entrada_stall.repeticoes == 1
    assert entrada_stall.proxima_revisao == T0 + timedelta(days=1)

    (terceira,) = await m.diz("0")
    assert terceira.startswith("🎉 *Practice done* — 1 reviewed.")
    assert "✅ Solid: stall" in terceira
    assert "Send me a new word" in terceira
    assert m.repo.obter_sessao().estado == Estado.IDLE


async def test_de_novo_volta_para_o_fim_da_fila_da_sessao() -> None:
    m = await _com_stall_e_hedge_vencidas()
    m.tutor.revisoes = [
        Revisao(tipo="nao_sei", qualidade="de_novo", feedback="No worries, let's see it again."),
        Revisao(tipo="definicao", qualidade="bom", feedback="Got it."),
        Revisao(tipo="definicao", qualidade="bom", feedback="Good."),
    ]
    await m.diz("/revisar")

    (apos_de_novo,) = await m.diz("I don't know")
    assert "No worries" in apos_de_novo
    assert "🔁 2/2 · *hedge*" in apos_de_novo

    (apos_hedge,) = await m.diz("to protect against loss")
    # stall voltou para o fim da fila desta sessão: aparece de novo.
    assert "*stall*" in apos_hedge

    entrada_stall = m.repo.obter_entrada("stall")
    assert entrada_stall is not None
    assert entrada_stall.lapsos == 1
    assert entrada_stall.repeticoes == 0

    (resumo,) = await m.diz("the talks stalled")
    assert "🎉 *Practice done*" in resumo
    assert "🔁 Coming back soon: stall" in resumo


async def test_entrada_apagada_no_meio_da_revisao_e_pulada() -> None:
    m = await _com_stall_e_hedge_vencidas()
    m.tutor.revisoes = [Revisao(tipo="definicao", qualidade="bom", feedback="Nice.")]
    await m.diz("/revisar")

    m.repo.apagar_entrada("hedge")

    (resposta,) = await m.diz("to stop making progress")
    assert "🎉 *Practice done*" in resposta


async def test_cancelar_durante_a_revisao_fecha_com_o_resumo() -> None:
    m = await _com_stall_e_hedge_vencidas()
    await m.diz("/revisar")

    (resposta,) = await m.diz("/cancelar")

    assert "🎉 *Practice done*" in resposta or "No pending reviews" in resposta
    assert m.repo.obter_sessao().estado == Estado.IDLE


async def test_frase_da_revisao_guarda_a_versao_corrigida() -> None:
    m = await _com_stall_e_hedge_vencidas()
    await m.diz("/review")
    m.tutor.revisoes.append(
        Revisao(
            tipo="frase",
            qualidade="bom",
            feedback="Nice!",
            correcao="The talks [[stalled]] for weeks.",
        )
    )

    await m.diz("the talks stalled for weeks")

    (frase,) = m.repo.listar_frases("stall")
    assert frase.autor == "usuario"
    assert frase.versao_natural == "The talks [[stalled]] for weeks."
