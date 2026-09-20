"""Comandos (seção 5.2): /ajuda /lista /pendentes /praticar /exportar /apagar /nivel /cancelar /status."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Protocol, get_args

from app import messages
from app.domain.choices import normalizar
from app.domain.models import Entry, NivelUsuario, Profile, Sessao, slugify
from app.flows import capture
from app.flows.base import Deps, bloq
from app.repo.base import Repository

logger = logging.getLogger(__name__)

_NIVEIS: tuple[str, ...] = get_args(NivelUsuario)


class Exportador(Protocol):
    """Gera o arquivo do Anki e devolve (link, quantidade de cartões); `None` se não há nada
    a exportar. Síncrono, como o resto do acesso a Firestore/Storage."""

    def exportar(self, *, tudo: bool) -> tuple[str, int] | None: ...


StatusDaSessao = Callable[[], Awaitable[str]]


async def executar(
    d: Deps,
    sessao: Sessao,
    perfil: Profile,
    texto: str,
    *,
    status_da_sessao: StatusDaSessao | None,
    exportador: Exportador | None,
) -> Sessao:
    partes = texto.strip()[1:].split(maxsplit=1)
    comando = normalizar(partes[0]) if partes else ""
    argumento = partes[1].strip() if len(partes) > 1 else ""
    conversa = d.conversa

    if comando == "ajuda":
        await conversa.enviar(messages.AJUDA)
    elif comando == "lista":
        entradas = await bloq(d.repo.listar_entradas)
        await conversa.enviar(messages.lista(entradas) if entradas else messages.SEM_ENTRADAS)
    elif comando == "pendentes":
        pendentes = await bloq(d.repo.listar_entradas, "nova")
        await conversa.enviar(
            messages.pendentes(pendentes) if pendentes else messages.SEM_PENDENTES
        )
    elif comando == "praticar":
        return await _praticar(d, sessao, perfil, argumento)
    elif comando == "exportar":
        await _exportar(d, argumento, exportador)
    elif comando == "apagar":
        return await _apagar(d, sessao, argumento)
    elif comando == "nivel":
        await _nivel(d, perfil, argumento)
    elif comando == "cancelar":
        await conversa.enviar(messages.CANCELADO)
        return d.sessao_vazia()
    elif comando == "status":
        await _status(d, status_da_sessao)
    else:
        await conversa.enviar(messages.COMANDO_DESCONHECIDO)
    return sessao


def _achar_entrada(repo: Repository, palavra: str) -> Entry | None:
    direta = repo.obter_entrada(slugify(palavra))
    if direta is not None:
        return direta
    alvo = normalizar(palavra)
    return next((e for e in repo.listar_entradas() if normalizar(e.palavra) == alvo), None)


async def _praticar(d: Deps, sessao: Sessao, perfil: Profile, palavra: str) -> Sessao:
    if palavra:
        entrada = await bloq(_achar_entrada, d.repo, palavra)
        if entrada is None:
            await d.conversa.enviar(messages.palavra_nao_encontrada(palavra))
            return sessao
    else:
        pendentes = await bloq(d.repo.listar_entradas, "nova")
        if not pendentes:
            await d.conversa.enviar(messages.SEM_PENDENTES)
            return sessao
        entrada = pendentes[0]
    return await capture.explicar(d, perfil, entrada.palavra, entrada_existente=entrada)


async def _exportar(d: Deps, argumento: str, exportador: Exportador | None) -> None:
    if exportador is None:
        await d.conversa.enviar(messages.EXPORTACAO_INDISPONIVEL)
        return
    async with d.conversa.digitando():
        resultado = await bloq(exportador.exportar, tudo=normalizar(argumento) == "tudo")
    if resultado is None:
        await d.conversa.enviar(messages.SEM_EXPORTAVEIS)
        return
    link, quantidade = resultado
    await d.conversa.enviar(messages.exportacao(link, quantidade))


async def _apagar(d: Deps, sessao: Sessao, palavra: str) -> Sessao:
    if not palavra:
        await d.conversa.enviar(messages.COMANDO_DESCONHECIDO)
        return sessao
    entrada = await bloq(_achar_entrada, d.repo, palavra)
    if entrada is None:
        await d.conversa.enviar(messages.palavra_nao_encontrada(palavra))
        return sessao
    await bloq(d.repo.apagar_entrada, entrada.slug)
    await d.conversa.enviar(messages.apagada(entrada.palavra))
    # Se era a palavra em andamento, a conversa não pode continuar apontando para o nada.
    return d.sessao_vazia() if sessao.entry_id == entrada.slug else sessao


async def _nivel(d: Deps, perfil: Profile, argumento: str) -> None:
    if not argumento:
        await d.conversa.enviar(messages.nivel_atual(perfil.nivel))
        return
    escolhido = argumento.strip().upper()
    if escolhido not in _NIVEIS:
        await d.conversa.enviar(messages.nivel_invalido())
        return
    novo = perfil.model_copy(update={"nivel": escolhido})
    await bloq(d.repo.salvar_perfil, novo)
    await d.conversa.enviar(messages.nivel_alterado(novo.nivel))


async def _status(d: Deps, status_da_sessao: StatusDaSessao | None) -> None:
    try:
        sessao_waha = await status_da_sessao() if status_da_sessao else "desconhecido"
    except Exception:  # o /status existe justamente para funcionar quando algo está quebrado
        logger.warning("não consegui consultar a sessão do WAHA", exc_info=True)
        sessao_waha = "indisponível"
    entradas = await bloq(d.repo.listar_entradas)
    pendentes = sum(1 for e in entradas if e.status == "nova")
    await d.conversa.enviar(messages.status(sessao_waha, len(entradas), pendentes))
