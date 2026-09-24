"""Roteador: recebe o texto do aluno, decide (máquina de estados pura, ADR-0004/ADR-0009),
executa a ação com os fluxos e guarda a sessão.

Multiusuário (ADR-0017): cada chat é um espaço, com o próprio caderno (`Banco.do_espaco`), a
própria `Conversa` (e o limite de 3 mensagens seguidas) e a própria trava. Duas mensagens do mesmo
chat andam uma por vez; chats diferentes andam em paralelo."""

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
from app.flows import capture, commands, freeform, practice, review, song, synonyms
from app.flows.base import FUSO_PADRAO, Deps, bloq
from app.flows.commands import Exportador, StatusDaSessao
from app.flows.conversa import Conversa
from app.repo.base import Banco
from app.services.letras import LyricsProvider
from app.services.llm import LLMError, Tutor

logger = logging.getLogger(__name__)


class Router:
    def __init__(
        self,
        *,
        banco: Banco,
        tutor: Tutor,
        criar_conversa: Callable[[str], Conversa],
        nivel_padrao: NivelUsuario,
        agora: Callable[[], datetime] = agora_utc,
        status_da_sessao: StatusDaSessao | None = None,
        exportador: Exportador | None = None,
        fuso: ZoneInfo = FUSO_PADRAO,
        letras: LyricsProvider | None = None,
    ) -> None:
        self._banco = banco
        self._tutor = tutor
        self._criar_conversa = criar_conversa
        self._agora = agora
        self._fuso = fuso
        self._letras = letras
        self._nivel_padrao = nivel_padrao
        self._status_da_sessao = status_da_sessao
        self._exportador = exportador
        self._conversas: dict[str, Conversa] = {}
        # O webhook pode chegar em duas mensagens seguidas do mesmo chat: uma por vez.
        self._travas: dict[str, asyncio.Lock] = {}

    def conversa_do(self, chat_id: str) -> Conversa:
        if chat_id not in self._conversas:
            self._conversas[chat_id] = self._criar_conversa(chat_id)
        return self._conversas[chat_id]

    def _trava(self, chat_id: str) -> asyncio.Lock:
        return self._travas.setdefault(chat_id, asyncio.Lock())

    def _deps(self, chat_id: str) -> Deps:
        return Deps(
            repo=self._banco.do_espaco(chat_id),
            tutor=self._tutor,
            conversa=self.conversa_do(chat_id),
            agora=self._agora,
            fuso=self._fuso,
            letras=self._letras,
        )

    async def midia_nao_suportada(self, chat_id: str) -> None:
        async with self._trava(chat_id):
            conversa = self.conversa_do(chat_id)
            conversa.usuario_falou()
            await conversa.enviar(messages.MIDIA_NAO_SUPORTADA)

    async def processar(self, texto: str, chat_id: str) -> None:
        """`chat_id` é o espaço E o destino das respostas: o chat de onde a mensagem veio."""
        async with self._trava(chat_id):
            d = self._deps(chat_id)
            d.conversa.usuario_falou()
            perfil = await bloq(self._perfil, d)
            if perfil.chat_id != chat_id or perfil.lembrete_sem_resposta:
                # M10: guarda o destino real (para o agendador saber para onde mandar os
                # lembretes) e limpa o backoff — o aluno acabou de falar.
                perfil = perfil.model_copy(
                    update={"chat_id": chat_id, "lembrete_sem_resposta": False}
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
                    nova = await self._conversar(d, sessao, perfil, texto)
            except LLMError:
                logger.warning("falha da IA; sessão mantida como estava", exc_info=True)
                await d.conversa.enviar(messages.ERRO_IA)
                return

            await bloq(d.repo.salvar_sessao, nova.model_copy(update={"atualizado_em": d.agora()}))

    def _perfil(self, d: Deps) -> Profile:
        perfil = d.repo.obter_perfil()
        if perfil is None:
            perfil = Profile(nivel=self._nivel_padrao, criado_em=d.agora())
            d.repo.salvar_perfil(perfil)
        return perfil

    async def _conversar(self, d: Deps, sessao: Sessao, perfil: Profile, texto: str) -> Sessao:
        transicao = transicionar(Estado(sessao.estado), texto)
        sessao = sessao.model_copy(update={"estado": transicao.estado})
        return await self._executar(d, transicao, sessao, perfil)

    async def _executar(self, d: Deps, t: Transicao, sessao: Sessao, perfil: Profile) -> Sessao:
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
            case Acao.BUSCAR_MUSICA:
                return await song.buscar(d, sessao, str(argumento))
            case Acao.ESCOLHER_MUSICA:
                return await song.escolher(d, sessao, str(argumento))
            case Acao.CANCELAR_MUSICA:
                return await song.cancelar(d)
            case Acao.RESPONDER_VERSO:
                return await song.responder(d, sessao, perfil, str(argumento))
            case Acao.ENCERRAR_MUSICA:
                return await song.encerrar(d, sessao)
            case Acao.SALVAR_EXPRESSOES:
                return await song.salvar(d, sessao, perfil, str(argumento))
            case Acao.DESCARTAR_EXPRESSOES:
                return await song.descartar(d)

    async def iniciar_revisao(self, chat_id: str) -> None:
        """Chamado pelo agendador (M10, `app/services/lembretes.py`): o bot inicia a conversa,
        não responde a uma. Mesma trava do resto (não pode correr junto de uma mensagem
        chegando). Nunca dispara sem um destino real já aprendido, e nunca interrompe uma
        conversa em andamento — quem decide isso é o próprio agendador, antes de chamar."""
        async with self._trava(chat_id):
            d = self._deps(chat_id)
            perfil = await bloq(self._perfil, d)
            if perfil.chat_id is None:
                return
            sessao = await bloq(d.repo.obter_sessao)
            if sessao.estado != Estado.IDLE:
                return
            nova = await review.iniciar(d)
            await bloq(d.repo.salvar_sessao, nova.model_copy(update={"atualizado_em": d.agora()}))
