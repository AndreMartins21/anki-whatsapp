"""Testes do envio de arquivo pela `Conversa` (M12): mesmo ritmo humano e mesmo limite do texto."""

from __future__ import annotations

import pytest

from app.channel.fake import FakeChannel
from app.flows.conversa import Conversa

CHAT = "5531999998888@c.us"


async def _sem_espera(_: float) -> None:
    return None


def _conversa(canal: FakeChannel, **kwargs: int) -> Conversa:
    return Conversa(canal, CHAT, dormir=_sem_espera, atraso=lambda: 0.0, **kwargs)


async def test_enviar_arquivo_manda_para_o_destino_com_a_legenda() -> None:
    canal = FakeChannel()

    await _conversa(canal).enviar_arquivo("a.xlsx", b"dados", "application/x-teste", "oi")

    assert canal.arquivos_enviados == [(CHAT, "a.xlsx", b"dados", "oi")]


async def test_arquivo_conta_no_limite_de_mensagens_seguidas() -> None:
    canal = FakeChannel()
    conversa = _conversa(canal, max_seguidas=1)

    await conversa.enviar_arquivo("a.xlsx", b"1", "t")
    await conversa.enviar_arquivo("b.xlsx", b"2", "t")  # descartado: já falou 1 vez sem resposta

    assert [a[1] for a in canal.arquivos_enviados] == ["a.xlsx"]


async def test_falha_no_envio_do_arquivo_sobe_a_excecao_e_nao_conta() -> None:
    canal = FakeChannel(falha_no_arquivo=True)
    conversa = _conversa(canal, max_seguidas=1)

    with pytest.raises(RuntimeError):
        await conversa.enviar_arquivo("a.xlsx", b"1", "t")
    await conversa.enviar("texto de plano B")  # ainda cabe: a falha não consumiu o limite

    assert canal.textos_enviados == [(CHAT, "texto de plano B")]
