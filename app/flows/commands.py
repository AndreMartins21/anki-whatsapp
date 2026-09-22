"""Comandos (seção 5.2): /help /list /pending /practice /export /delete /level /cancel /status.

Cada comando aceita o nome em inglês e o apelido em PT-BR que a spec sempre teve (`/praticar`,
`/lista`...), já que o Case D de salvar ("Practice it any time with /praticar stall") cita os
nomes em português."""

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
from app.services.anki import ResultadoExportacao

logger = logging.getLogger(__name__)

_NIVEIS: tuple[str, ...] = get_args(NivelUsuario)

_AJUDA = {"ajuda", "help"}
_LISTA = {"lista", "list"}
_PENDENTES = {"pendentes", "pending"}
_PRATICAR = {"praticar", "practice"}
_EXPORTAR = {"exportar", "export"}
_APAGAR = {"apagar", "delete"}
_NIVEL = {"nivel", "level"}
_CANCELAR = {"cancelar", "cancel"}
_STATUS = {"status"}


class Exportador(Protocol):
    """Gera o arquivo do Anki e devolve o resultado; `None` se não há nada a exportar.
    Síncrono, como o resto do acesso a Firestore/Storage."""

    def exportar(self, *, tudo: bool) -> ResultadoExportacao | None: ...


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

    if comando in _AJUDA:
        await conversa.enviar(messages.AJUDA)
    elif comando in _LISTA:
        entradas = await bloq(d.repo.listar_entradas)
        await conversa.enviar(messages.lista(entradas) if entradas else messages.SEM_ENTRADAS)
    elif comando in _PENDENTES:
        pendentes = await bloq(d.repo.listar_entradas, "nova")
        await conversa.enviar(
            messages.pendentes(pendentes) if pendentes else messages.SEM_PENDENTES
        )
    elif comando in _PRATICAR:
        return await _praticar(d, sessao, perfil, argumento)
    elif comando in _EXPORTAR:
        await _exportar(d, argumento, exportador)
    elif comando in _APAGAR:
        return await _apagar(d, sessao, argumento)
    elif comando in _NIVEL:
        await _nivel(d, perfil, argumento)
    elif comando in _CANCELAR:
        await conversa.enviar(messages.CANCELADO)
        return d.sessao_vazia()
    elif comando in _STATUS:
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
        resultado = await bloq(exportador.exportar, tudo=normalizar(argumento) in {"tudo", "all"})
    if resultado is None:
        await d.conversa.enviar(messages.SEM_EXPORTAVEIS)
        return
    await d.conversa.enviar(
        messages.exportacao(resultado.link, resultado.quantidade, resultado.ignoradas)
    )


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
        sessao_waha = await status_da_sessao() if status_da_sessao else "unknown"
    except Exception:  # o /status existe justamente para funcionar quando algo está quebrado
        logger.warning("não consegui consultar a sessão do WAHA", exc_info=True)
        sessao_waha = "unavailable"
    entradas = await bloq(d.repo.listar_entradas)
    pendentes = sum(1 for e in entradas if e.status == "nova")
    await d.conversa.enviar(messages.status(sessao_waha, len(entradas), pendentes))
