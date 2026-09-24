"""M17: o FakeChannel registra as menções para os testes e o ConsoleChannel mostra `@nome`."""

from __future__ import annotations

from app.channel.console import ConsoleChannel
from app.channel.fake import FakeChannel


async def test_fake_channel_registra_as_mencoes_de_cada_texto() -> None:
    canal = FakeChannel()

    await canal.send_text("g@g.us", "@5531999998888 vez sua", mentions=["5531999998888"])
    await canal.send_text("g@g.us", "sem menção")

    assert canal.textos_enviados == [("g@g.us", "@5531999998888 vez sua"), ("g@g.us", "sem menção")]
    assert canal.mencoes_enviadas == [("g@g.us", ("5531999998888",))]


async def test_fake_channel_devolve_os_participantes_configurados() -> None:
    canal = FakeChannel(participantes_de_grupos={"g@g.us": ["5531999998888"]})

    assert await canal.group_participants("g@g.us") == ["5531999998888"]
    assert await canal.group_participants("outro@g.us") == []


async def test_console_mostra_o_nome_no_lugar_do_numero_da_mencao() -> None:
    saida: list[str] = []
    canal = ConsoleChannel(saida.append, nomes={"5531999998888": "ana"})

    await canal.send_text("g@g.us", "@5531999998888 your turn", mentions=["5531999998888"])

    assert "@ana your turn" in saida[0] and "5531999998888" not in saida[0]


async def test_console_sem_nome_conhecido_mostra_o_texto_como_veio() -> None:
    saida: list[str] = []
    canal = ConsoleChannel(saida.append)

    await canal.send_text("g@g.us", "@5531999998888 your turn", mentions=["5531999998888"])

    assert "@5531999998888 your turn" in saida[0]
