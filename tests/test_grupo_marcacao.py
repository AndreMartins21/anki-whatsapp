"""M37 (ADR-0035): em grupo o bot responde a quem o marca, sem comando; os comandos seguem com `!`
ou `/`. O filtro está no webhook (marcação em `mentionedIds`, número ou LID, ou escrita no texto);
o fluxo recebe o texto já sem a marcação."""

from __future__ import annotations

import logging
from typing import Any

import pytest

from app import messages
from app.domain.models import Estado
from app.flows import grupo
from app.flows.base import Autor
from app.services.fake_llm import FakeTutor
from tests.helpers import GRUPO, eventos, expansoes, explicacao_stall, montar
from tests.webhook_helpers import GRUPO_FIXO, Ambiente, _do_grupo

ANA = "5531999998888"
BOT = "5531988887777"
LID_DO_BOT = "99887766@lid"


def _marcando(texto: str, *, ids: list[str] | None = None, remetente: str = ANA) -> dict[str, Any]:
    corpo = _do_grupo(GRUPO_FIXO, f"{remetente}@c.us", texto)
    if ids is not None:
        corpo["payload"]["mentionedIds"] = ids
    return corpo


# --- helpers puros ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("!list", "list"),
        ("/list", "list"),
        ("/1", "1"),
        ("  /skip  ", "skip"),
        ("!!!", None),
        ("/", None),
        ("/ oi", None),
        ("bom dia", None),
        ("and/or", None),
    ],
)
def test_sem_prefixo_aceita_exclamacao_e_barra(texto: str, esperado: str | None) -> None:
    assert grupo.sem_prefixo(texto, "!") == esperado


def test_sem_marcacao_tira_so_as_do_bot() -> None:
    texto = "@99887766 stall | the talks stalled @5531999990000"

    assert grupo.sem_marcacao(texto, {"99887766"}) == "stall | the talks stalled @5531999990000"
    assert grupo.sem_marcacao("stall @99887766", {"99887766"}) == "stall"
    assert grupo.sem_marcacao("@99887766", {"99887766"}) == ""


# --- webhook ----------------------------------------------------------------------------------


def test_marcar_o_bot_com_uma_palavra_adiciona_a_palavra(ambiente: Ambiente) -> None:
    ambiente.tutor.expansoes.append(expansoes())

    ambiente.cliente.post(
        "/waha/webhook", json=_marcando(f"@{BOT} stall | the talks stalled", ids=[f"{BOT}@c.us"])
    )

    ((chat, texto),) = ambiente.canal.textos_enviados
    assert chat == GRUPO_FIXO and "*stall*" in texto and "tag me" in texto
    assert [e.slug for e in ambiente.banco.do_espaco(GRUPO_FIXO).listar_entradas()] == ["stall"]
    assert ambiente.canal.vistos == [GRUPO_FIXO]
    membro = ambiente.banco.do_espaco(GRUPO_FIXO).obter_membro(ANA)
    assert membro is not None and membro.papel == "aluno"


def test_marcacao_pelo_lid_do_bot_e_resolvida(ambiente: Ambiente) -> None:
    ambiente.canal.lids_conhecidos[LID_DO_BOT] = BOT

    ambiente.cliente.post("/waha/webhook", json=_marcando("@99887766 stall", ids=[LID_DO_BOT]))

    ((_, texto),) = ambiente.canal.textos_enviados
    assert "*stall*" in texto  # o `@99887766` do texto foi tirado, a palavra ficou


def test_marcacao_escrita_com_o_numero_do_bot_basta_sem_mentioned_ids(
    ambiente: Ambiente,
) -> None:
    ambiente.cliente.post("/waha/webhook", json=_marcando(f"@{BOT} stall"))

    ((_, texto),) = ambiente.canal.textos_enviados
    assert "*stall*" in texto


def test_marcacao_sem_o_nono_digito_tambem_vale(ambiente: Ambiente) -> None:
    sem_nono = BOT[:4] + BOT[5:]

    ambiente.cliente.post("/waha/webhook", json=_marcando(f"@{sem_nono} stall"))

    assert len(ambiente.canal.textos_enviados) == 1


def test_so_marcar_o_bot_mostra_a_ajuda(ambiente: Ambiente) -> None:
    ambiente.cliente.post("/waha/webhook", json=_marcando(f"@{BOT}", ids=[f"{BOT}@c.us"]))

    assert ambiente.canal.textos_enviados == [(GRUPO_FIXO, messages.ajuda_do_grupo("!"))]


def test_marcar_outra_pessoa_nao_chama_o_bot(ambiente: Ambiente) -> None:
    ambiente.cliente.post(
        "/waha/webhook",
        json=_marcando("@5511977776666 você viu o stall?", ids=["5511977776666@c.us"]),
    )

    assert ambiente.canal.textos_enviados == [] and ambiente.canal.vistos == []
    assert ambiente.banco.do_espaco(GRUPO_FIXO).listar_membros() == []


def test_conversa_sem_marcacao_nada_gravado_nada_enviado(ambiente: Ambiente) -> None:
    ambiente.cliente.post("/waha/webhook", json=_marcando("gente, alguém entendeu a aula?"))

    assert ambiente.canal.textos_enviados == [] and ambiente.canal.vistos == []
    assert ambiente.banco.do_espaco(GRUPO_FIXO).listar_membros() == []


def test_marcar_o_bot_em_grupo_nao_ativado_e_ignorado(ambiente: Ambiente) -> None:
    corpo = _do_grupo("120363000000000555@g.us", f"{ANA}@c.us", f"@{BOT} stall")
    corpo["payload"]["mentionedIds"] = [f"{BOT}@c.us"]

    ambiente.cliente.post("/waha/webhook", json=corpo)

    assert ambiente.canal.textos_enviados == [] and ambiente.canal.vistos == []


def test_comando_marcando_o_bot_segue_sendo_comando(ambiente: Ambiente) -> None:
    ambiente.cliente.post("/waha/webhook", json=_marcando(f"@{BOT} !help", ids=[f"{BOT}@c.us"]))

    assert ambiente.canal.textos_enviados == [(GRUPO_FIXO, messages.ajuda_do_grupo("!"))]


def test_barra_e_comando_no_grupo_pelo_webhook(ambiente: Ambiente) -> None:
    ambiente.cliente.post("/waha/webhook", json=_marcando("/help"))

    assert ambiente.canal.textos_enviados == [(GRUPO_FIXO, messages.ajuda_do_grupo("!"))]


def test_marcacao_registra_o_evento_sem_o_texto(
    ambiente: Ambiente, caplog: pytest.LogCaptureFixture
) -> None:
    ambiente.tutor.expansoes.append(expansoes())
    with caplog.at_level(logging.INFO):
        ambiente.cliente.post("/waha/webhook", json=_marcando(f"@{BOT} stall", ids=[f"{BOT}@c.us"]))

    (evento,) = eventos(caplog.records, "mensagem_recebida")
    assert (evento.tipo_espaco, evento.comando) == ("grupo", "marcacao")
    assert "stall" not in str(vars(evento))


def test_responder_uma_revisao_marcando_o_bot(ambiente: Ambiente) -> None:
    from app.domain.models import Revisao

    ambiente.tutor.expansoes.append(expansoes())
    ambiente.tutor.revisoes.append(Revisao(tipo="definicao", qualidade="bom", feedback="Nice!"))
    ambiente.canal.participantes_de_grupos[GRUPO_FIXO] = [ANA]
    for texto in ("!add stall", "!4", "!review"):
        ambiente.cliente.post("/waha/webhook", json=_marcando(texto))

    ambiente.cliente.post(
        "/waha/webhook", json=_marcando(f"@{BOT} it means to stop", ids=[f"{BOT}@c.us"])
    )

    assert "Practice done" in ambiente.canal.textos_enviados[-1][1]
    # e a conversa solta durante a revisão não é lida
    antes = len(ambiente.canal.textos_enviados)
    ambiente.cliente.post("/waha/webhook", json=_marcando("hahaha"))
    assert len(ambiente.canal.textos_enviados) == antes


# --- fluxo (sem webhook) ----------------------------------------------------------------------

AUTOR = Autor(numero=ANA, nome="Ana")


async def test_marcar_com_menu_numero_escolhe_a_opcao() -> None:
    m = montar(
        tutor=FakeTutor(explicacoes=[explicacao_stall()], expansoes=[expansoes()]),
    )
    await m.diz_no_grupo(AUTOR, "!add stall")

    (resposta,) = await m.marca_no_grupo(AUTOR, "4")

    assert resposta.startswith("✅ Saved")
    assert m.banco.do_espaco(GRUPO).obter_sessao().estado == Estado.IDLE


async def test_marcar_sem_texto_e_pedir_ajuda_e_help_marcado_tambem() -> None:
    m = montar(tutor=FakeTutor())

    assert await m.marca_no_grupo(AUTOR, "") == [messages.ajuda_do_grupo("!")]
    assert await m.marca_no_grupo(AUTOR, "help") == [messages.ajuda_do_grupo("!")]
    assert m.tutor.chamadas == []
