"""Roteador: recebe o texto do aluno, decide (máquina de estados pura, ADR-0004/ADR-0009),
executa a ação com os fluxos e guarda a sessão."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from app import messages
from app.domain.models import (
    Estado,
    NivelUsuario,
    Profile,
    Sessao,
    agora_utc,
)
from app.domain.state import Acao, Transicao, expirou, transicionar
from app.flows import capture, commands, freeform, practice, review, synonyms
from app.flows.base import FUSO_PADRAO, Deps, bloq
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
        agora: Callable[[], datetime] = agora_utc,
        status_da_sessao: StatusDaSessao | None = None,
        exportador: Exportador | None = None,
        fuso: ZoneInfo = FUSO_PADRAO,
    ) -> None:
        self._d = Deps(repo=repo, tutor=tutor, conversa=conversa, agora=agora, fuso=fuso)
        self._nivel_padrao = nivel_padrao
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
            if destino and (perfil.chat_id != destino or perfil.lembrete_sem_resposta):
                # M10: guarda o destino real (para o agendador saber para onde mandar os
                # lembretes) e limpa o backoff — o aluno acabou de falar.
                perfil = perfil.model_copy(
                    update={"chat_id": destino, "lembrete_sem_resposta": False}
                )
                await bloq(d.repo.salvar_perfil, perfil)
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
            perfil = Profile(nivel=self._nivel_padrao, criado_em=self._d.agora())
            repo.salvar_perfil(perfil)
        return perfil

    async def _conversar(self, sessao: Sessao, perfil: Profile, texto: str) -> Sessao:
        transicao = transicionar(Estado(sessao.estado), texto)
        sessao = sessao.model_copy(update={"estado": transicao.estado})
        return await self._executar(transicao, sessao, perfil)

    async def _executar(self, t: Transicao, sessao: Sessao, perfil: Profile) -> Sessao:
        d = self._d
        argumento = t.argumento
        match t.acao:
            case Acao.EXPLICAR:
                return await capture.explicar(d, perfil, str(argumento))
            case Acao.GERAR_EXEMPLOS:
                return await practice.gerar_exemplos(d, sessao, perfil)
            case Acao.GERAR_SINONIMOS:
                return await synonyms.gerar(d, sessao, perfil)
            case Acao.SALVAR:
                return await practice.concluir(d, sessao, perfil)
            case Acao.ROTEAR:
                return await freeform.rotear(d, sessao, perfil, str(argumento))
            case Acao.RESPONDER_REVISAO:
                return await review.responder(d, sessao, perfil, str(argumento))
            case Acao.ENCERRAR_REVISAO:
                return await review.encerrar(d, sessao)

    async def iniciar_revisao(self) -> None:
        """Chamado pelo agendador (M10, `app/services/lembretes.py`): o bot inicia a conversa,
        não responde a uma. Mesma trava do resto (não pode correr junto de uma mensagem
        chegando). Nunca dispara sem um destino real já aprendido, e nunca interrompe uma
        conversa em andamento — quem decide isso é o próprio agendador, antes de chamar."""
        async with self._trava:
            d = self._d
            perfil = await bloq(self._perfil)
            if perfil.chat_id is None:
                return
            sessao = await bloq(d.repo.obter_sessao)
            if sessao.estado != Estado.IDLE:
                return
            d.conversa.definir_destino(perfil.chat_id)
            nova = await review.iniciar(d)
            await bloq(d.repo.salvar_sessao, nova.model_copy(update={"atualizado_em": d.agora()}))
