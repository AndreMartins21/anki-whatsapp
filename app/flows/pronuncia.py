"""Pronúncia em áudio (M23, ADR-0024): sob demanda, duas notas de voz — o termo e a frase de
exemplo que o bot deu no card. O áudio vem do cache (GCS) e só é sintetizado na primeira vez."""

from __future__ import annotations

import logging
from collections.abc import Callable

from app import messages
from app.domain.models import Entry, Sessao
from app.flows.base import Deps, bloq
from app.flows.practice import entrada_atual

logger = logging.getLogger(__name__)


async def ouvir_da_sessao(d: Deps, sessao: Sessao) -> Sessao:
    """Opção 1 do menu: a palavra aberta. Depois das duas vozes, o bot volta a perguntar o que o
    aluno quer fazer (as opções 2 a 5) e a conversa fica exatamente onde estava."""
    await ouvir(
        d,
        await entrada_atual(d, sessao),
        menu_depois=lambda entrada: messages.menu_depois_do_audio(
            entrada.palavra,
            ja_viu_sinonimos=bool(sessao.sinonimos_mostrados),
            grupo=d.grupo_prefixo,
        ),
    )
    return sessao


async def ouvir(
    d: Deps, entrada: Entry, *, menu_depois: Callable[[Entry], str] | None = None
) -> None:
    """Manda a voz do termo e a do exemplo. Com `menu_depois` (a palavra está aberta), fecha com o
    menu e só as 3 mensagens cabem no limite de seguidas; sem ele (`/listen`, que não abre a
    palavra), abre com um texto dizendo o que vem. Qualquer falha (TTS, Storage, WhatsApp) vira
    um aviso curto: o áudio é um extra, nunca derruba a conversa."""
    if d.audio is None:
        await d.conversa.enviar(messages.ERRO_AUDIO)
        return
    frases = await bloq(d.repo.listar_frases, entrada.slug)
    # O exemplo do card é a frase do bot mais antiga; as de "see more examples" vêm depois.
    exemplo = next((f.texto for f in frases if f.autor == "bot"), None)
    try:
        async with d.conversa.digitando():
            termo = await bloq(d.audio.obter, messages.sem_marcas(entrada.palavra))
            fala = await bloq(d.audio.obter, messages.sem_marcas(exemplo)) if exemplo else None
        if menu_depois is None:
            await d.conversa.enviar(messages.pronuncia(entrada.palavra, exemplo))
        await d.conversa.enviar_voz(termo.conteudo)
        if fala is not None:
            await d.conversa.enviar_voz(fala.conteudo)
        if menu_depois is not None:
            await d.conversa.enviar(menu_depois(entrada))
    except Exception:
        logger.warning("não consegui mandar o áudio de pronúncia", exc_info=True)
        await d.conversa.enviar(messages.ERRO_AUDIO)
        return
    novos = {
        "audio_palavra": termo.uri,
        "audio_exemplo": fala.uri if fala is not None else entrada.audio_exemplo,
    }
    if any(getattr(entrada, campo) != valor for campo, valor in novos.items()):
        await bloq(d.repo.salvar_entrada, entrada.model_copy(update=novos))
