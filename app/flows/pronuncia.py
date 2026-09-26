"""Pronúncia em áudio (M23, ADR-0024): sob demanda, duas notas de voz — o termo e a frase de
exemplo que o bot deu no card. O áudio vem do cache (GCS) e só é sintetizado na primeira vez."""

from __future__ import annotations

import logging

from app import messages
from app.domain.models import Entry, Sessao
from app.flows.base import Deps, bloq
from app.flows.practice import entrada_atual

logger = logging.getLogger(__name__)


async def ouvir_da_sessao(d: Deps, sessao: Sessao) -> Sessao:
    """Opção 1 do menu: a palavra aberta. A conversa fica exatamente onde estava."""
    await ouvir(d, await entrada_atual(d, sessao))
    return sessao


async def ouvir(d: Deps, entrada: Entry) -> None:
    """Manda o texto, a voz do termo e a voz do exemplo. Qualquer falha (TTS, Storage, WhatsApp)
    vira um aviso curto: o áudio é um extra, nunca derruba a conversa."""
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
        await d.conversa.enviar(messages.pronuncia(entrada.palavra, exemplo))
        await d.conversa.enviar_voz(termo.conteudo)
        if fala is not None:
            await d.conversa.enviar_voz(fala.conteudo)
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
