"""Roteador: recebe o texto do aluno, decide (máquina de estados pura, ADR-0004), executa a ação
com os fluxos e guarda a sessão."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime

from app import messages
from app.domain.models import (
    Estado,
    ModoPratica,
    NivelUsuario,
    Profile,
    Sessao,
    agora_utc,
)
from app.domain.state import Acao, Contexto, Transicao, expirou, transicionar
from app.flows import capture, commands, expansion, practice
from app.flows.base import Deps, bloq
from app.flows.commands import Exportador, StatusDaSessao
from app.flows.conversa import Conversa
from app.repo.base import Repository
from app.services.llm import LLMError, Tutor

logger = logging.getLogger(__name__)


class Router:
    def __init__(
        self,
        *,
        repo: Repository,
        tutor: Tutor,
        conversa: Conversa,
        nivel_padrao: NivelUsuario,
        modo: ModoPratica,
        agora: Callable[[], datetime] = agora_utc,
        status_da_sessao: StatusDaSessao | None = None,
        exportador: Exportador | None = None,
    ) -> None:
        self._d = Deps(repo=repo, tutor=tutor, conversa=conversa, agora=agora)
        self._nivel_padrao = nivel_padrao
        self._modo = modo
        self._status_da_sessao = status_da_sessao
        self._exportador = exportador
        # Uma conversa só, mas o webhook pode chegar em duas mensagens seguidas: uma por vez.
        self._trava = asyncio.Lock()

    async def midia_nao_suportada(self, destino: str | None = None) -> None:
        async with self._trava:
            if destino:
                self._d.conversa.definir_destino(destino)
            self._d.conversa.usuario_falou()
            await self._d.conversa.enviar(messages.MIDIA_NAO_SUPORTADA)

    async def processar(self, texto: str, destino: str | None = None) -> None:
        async with self._trava:
            d = self._d
            if destino:
                d.conversa.definir_destino(destino)
            d.conversa.usuario_falou()
            perfil = await bloq(self._perfil)
            sessao = await bloq(d.repo.obter_sessao)
            if sessao.estado != Estado.IDLE and expirou(sessao.atualizado_em, d.agora()):
                # Parada há mais de 3 horas: volta para IDLE. O que havia já está salvo.
                sessao = d.sessao_vazia()

            try:
                if texto.strip().startswith("/"):
                    nova = await commands.executar(
                        d,
                        sessao,
                        perfil,
                        texto,
                        status_da_sessao=self._status_da_sessao,
                        exportador=self._exportador,
                    )
                else:
                    nova = await self._conversar(sessao, perfil, texto)
            except LLMError:
                logger.warning("falha da IA; sessão mantida como estava", exc_info=True)
                await d.conversa.enviar(messages.ERRO_IA)
                return

            await bloq(d.repo.salvar_sessao, nova.model_copy(update={"atualizado_em": d.agora()}))

    def _perfil(self) -> Profile:
        repo = self._d.repo
        perfil = repo.obter_perfil()
        if perfil is None:
            perfil = Profile(nivel=self._nivel_padrao, modo=self._modo, criado_em=self._d.agora())
            repo.salvar_perfil(perfil)
        elif perfil.modo != self._modo:  # PRACTICE_MODE do ambiente vale sobre o que ficou salvo
            perfil = perfil.model_copy(update={"modo": self._modo})
            repo.salvar_perfil(perfil)
        return perfil

    async def _conversar(self, sessao: Sessao, perfil: Profile, texto: str) -> Sessao:
        contexto = await bloq(self._contexto, sessao, perfil)
        transicao = transicionar(Estado(sessao.estado), texto, contexto)
        if transicao.estado is not None:
            sessao = sessao.model_copy(update={"estado": transicao.estado})
        return await self._executar(transicao, sessao, perfil)

    def _contexto(self, sessao: Sessao, perfil: Profile) -> Contexto:
        pendente = sessao.explicacao_pendente
        palavra: str | None = None
        if sessao.estado == Estado.AWAIT_SENSE and pendente is not None:
            palavra = pendente.palavra
        elif sessao.entry_id:
            entrada = self._d.repo.obter_entrada(sessao.entry_id)
            palavra = entrada.palavra if entrada else None
        return Contexto(
            palavra_alvo=palavra,
            n_sentidos=len(pendente.sentidos) if pendente else 0,
            n_expansoes=len(sessao.expansoes_sugeridas),
            modo=perfil.modo,
        )

    async def _executar(self, t: Transicao, sessao: Sessao, perfil: Profile) -> Sessao:
        d = self._d
        argumento = t.argumento
        match t.acao:
            case Acao.EXPLICAR:
                return await capture.explicar(d, perfil, str(argumento))
            case Acao.ESCOLHER_SENTIDO:
                return await capture.escolher_sentido(d, sessao, perfil, int(str(argumento)))
            case Acao.PEDIR_FRASE:
                return await practice.pedir_frase(d, sessao, perfil)
            case Acao.GERAR_EXEMPLOS:
                return await practice.gerar_exemplos(d, sessao, perfil)
            case Acao.SALVAR:
                return await practice.concluir(d, sessao, perfil, oferecer_expansoes=True)
            case Acao.AVALIAR:
                return await practice.avaliar(d, sessao, perfil, str(argumento))
            case Acao.PERGUNTAR_NOVA_PALAVRA:
                return await capture.perguntar_nova_palavra(d, sessao, str(argumento))
            case Acao.SALVAR_E_EXPLICAR_NOVA:
                nova_palavra = sessao.pendente_nova_palavra or ""
                if sessao.explicacao_pendente is None:  # com sentido escolhido há o que salvar
                    await practice.concluir(d, sessao, perfil, oferecer_expansoes=False)
                return await capture.explicar(d, perfil, nova_palavra)
            case Acao.AVALIAR_FRASE_PENDENTE:
                if sessao.explicacao_pendente is not None:
                    # Ainda falta escolher o sentido: sem ele não há como avaliar a frase.
                    voltando = sessao.model_copy(
                        update={"estado": Estado.AWAIT_SENSE, "pendente_nova_palavra": None}
                    )
                    await d.conversa.enviar(
                        messages.lembrete(await bloq(self._menu_atual, voltando, perfil))
                    )
                    return voltando
                frase = sessao.pendente_nova_palavra or ""
                sem_pendencia = sessao.model_copy(update={"pendente_nova_palavra": None})
                return await practice.avaliar(d, sem_pendencia, perfil, frase)
            case Acao.CRIAR_EXPANSOES:
                numeros = argumento if isinstance(argumento, tuple) else ()
                return await expansion.criar(d, sessao, numeros)
            case Acao.PRATICAR_EXPANSAO_AGORA:
                return await expansion.praticar_agora(d, sessao, perfil)
            case Acao.ENCERRAR:
                await d.conversa.enviar(messages.ENCERRADO)
                return d.sessao_vazia()
            case Acao.REENVIAR_MENU:
                await d.conversa.enviar(
                    messages.lembrete(await bloq(self._menu_atual, sessao, perfil))
                )
                return sessao

    def _menu_atual(self, sessao: Sessao, perfil: Profile) -> str:
        estado = Estado(sessao.estado)
        entrada = self._d.repo.obter_entrada(sessao.entry_id) if sessao.entry_id else None
        palavra = entrada.palavra if entrada else ""
        pendente = sessao.explicacao_pendente
        match estado:
            case Estado.AWAIT_SENSE if pendente is not None:
                return messages.menu_sentidos(pendente.palavra, pendente.sentidos)
            case Estado.AWAIT_CHOICE:
                return messages.menu_escolha(palavra, perfil.modo)
            case Estado.AWAIT_SENTENCE:
                return messages.pedido_de_frase(palavra, perfil.modo)
            case Estado.AWAIT_NEXT:
                return messages.menu_proximo()
            case Estado.AWAIT_AFTER_EXAMPLES:
                return messages.menu_apos_exemplos()
            case Estado.AWAIT_NEW_WORD:
                return messages.menu_nova_palavra(sessao.pendente_nova_palavra or "")
            case Estado.OFFER_EXPANSION:
                return messages.menu_expansoes(sessao.expansoes_sugeridas)
            case Estado.AWAIT_EXPANSION_PRACTICE:
                return messages.menu_praticar_expansao()
            case _:
                return messages.AJUDA
