"""Pronúncia em áudio (M23/M25/M26, ADR-0024/ADR-0026/ADR-0027): a voz do termo, e a da frase de
exemplo quando faz sentido. O áudio vem do cache (GCS) e só é sintetizado na primeira vez.

Desde o M25 é automático ao explicar a palavra (`anunciar=False`, com a frase); desde o M26,
também automático em cada card de revisão (`anunciar=False`, só o termo, `com_frase=False`).
`/listen` continua chamando sob demanda (`anunciar=True`, o padrão, com a frase)."""

from __future__ import annotations

import logging

from app import messages
from app.domain.models import Entry
from app.flows.base import Deps, bloq

logger = logging.getLogger(__name__)


async def ouvir(d: Deps, entrada: Entry, *, anunciar: bool = True, com_frase: bool = True) -> None:
    """Manda a voz do termo e, com `com_frase` (padrão), a do exemplo. `anunciar=True` (`/listen`,
    sob demanda): avisa se o serviço de áudio não está disponível neste ambiente, e abre com um
    texto dizendo o que vem. `anunciar=False` (automático — M25 ao explicar, M26 na revisão): sem
    serviço configurado fica em silêncio — ninguém pediu áudio explicitamente, e o texto que já foi
    mandado basta. Qualquer falha de verdade (TTS, Storage, WhatsApp), com o serviço configurado,
    sempre avisa: o áudio é um extra, nunca derruba a conversa, mas quebrar em silêncio pareceria o
    bot ignorando o aluno. `com_frase=False` (M26: cada card de revisão) pula a frase de exemplo —
    é sobre lembrar o som do termo, não reouvir a frase toda de novo."""
    if d.audio is None:
        if anunciar:
            await d.conversa.enviar(messages.ERRO_AUDIO)
        return
    exemplo = None
    if com_frase:
        frases = await bloq(d.repo.listar_frases, entrada.slug)
        # O exemplo do card é a frase do bot mais antiga; as de "see more examples" vêm depois.
        exemplo = next((f.texto for f in frases if f.autor == "bot"), None)
    try:
        async with d.conversa.digitando():
            termo = await bloq(d.audio.obter, messages.sem_marcas(entrada.palavra))
            fala = await bloq(d.audio.obter, messages.sem_marcas(exemplo)) if exemplo else None
        if anunciar:
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
