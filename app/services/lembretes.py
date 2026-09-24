"""Agendador de lembretes de revisão espaçada (M10, seção 5.7, ADR-0012).

Um laço no próprio processo, acordando a cada minuto (`_tick`, testável isolado de `rodar`), com
o próximo horário persistido em `profile/me` de cada espaço — sobrevive a um restart do container.
Três camadas de segurança contra mandar mensagem sem o aluno pedir (seção 5.6), valendo por espaço
(ADR-0017): só dispara com um `chat_id` real já aprendido de uma mensagem recebida, nunca sem fila
(silêncio em vez de spam) e nunca dois lembretes seguidos sem resposta (`lembrete_sem_resposta`).
Uma consulta por tick devolve só os espaços vencidos, então o custo não cresce com o número de
alunos parados.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.domain.lembretes import proximo_horario
from app.domain.models import Estado, Profile
from app.flows import review
from app.flows.base import bloq
from app.flows.router import Router
from app.repo.base import Banco, Repository

logger = logging.getLogger(__name__)

INTERVALO_PADRAO_SEGUNDOS = 60
LIMITE_DE_ATRASO = timedelta(hours=2)


class Agendador:
    def __init__(
        self,
        *,
        router: Router,
        banco: Banco,
        agora: Callable[[], datetime],
        fuso: ZoneInfo,
        dormir: Callable[[float], Awaitable[None]] = asyncio.sleep,
        intervalo_segundos: float = INTERVALO_PADRAO_SEGUNDOS,
    ) -> None:
        self._router = router
        self._banco = banco
        self._agora = agora
        self._fuso = fuso
        self._dormir = dormir
        self._intervalo = intervalo_segundos
        self._parar = False

    def parar(self) -> None:
        self._parar = True

    async def rodar(self) -> None:
        """Laço principal; roda até `parar()` ser chamado (o `_lifespan` do FastAPI cancela a
        task no shutdown, o que já interrompe o `dormir` — `parar()` é o caminho ordenado)."""
        while not self._parar:
            try:
                await self._tick()
            except Exception:  # o agendador nunca pode derrubar o processo
                logger.exception("falha no tick do agendador de lembretes")
            await self._dormir(self._intervalo)

    async def _tick(self) -> None:
        agora_utc = self._agora()
        for espaco_id in await bloq(self._banco.listar_espacos_com_lembrete, agora_utc):
            try:
                await self._tick_espaco(espaco_id)
            except Exception:  # um espaço com problema não pode calar os outros
                logger.exception("falha no lembrete de um espaço; os demais seguem")

    async def _tick_espaco(self, espaco_id: str) -> None:
        repo = self._banco.do_espaco(espaco_id)
        perfil = await bloq(repo.obter_perfil)
        if perfil is None or perfil.lembretes_por_dia == 0 or perfil.chat_id is None:
            return

        agora_utc = self._agora()
        agora_local = agora_utc.astimezone(self._fuso)

        if perfil.proximo_lembrete is None:
            await self._agendar_proximo(repo, perfil, agora_local)
            return
        if agora_utc < perfil.proximo_lembrete:
            return  # ainda não deu a hora

        atrasado_demais = agora_utc - perfil.proximo_lembrete > LIMITE_DE_ATRASO
        if atrasado_demais or perfil.lembrete_sem_resposta:
            # desiste deste horário (atraso grande, ou o aluno não respondeu ao lembrete
            # anterior): recalcula o próximo, sem disparar de novo.
            await self._agendar_proximo(repo, perfil, agora_local)
            return

        sessao = await bloq(repo.obter_sessao)
        if sessao.estado != Estado.IDLE:
            return  # conversa em andamento: tenta de novo no próximo tick

        entradas = await bloq(repo.listar_entradas)
        if not review.montar_fila(entradas, agora_utc):
            # nada vencido agora: recalcula o próximo horário, sem marcar backoff nem mandar nada.
            await self._agendar_proximo(repo, perfil, agora_local)
            return

        await bloq(repo.salvar_perfil, perfil.model_copy(update={"lembrete_sem_resposta": True}))
        await self._router.iniciar_revisao(perfil.chat_id)

        perfil_apos = await bloq(repo.obter_perfil)
        if perfil_apos is not None:
            await self._agendar_proximo(repo, perfil_apos, agora_local)

    async def _agendar_proximo(
        self, repo: Repository, perfil: Profile, agora_local: datetime
    ) -> None:
        novo = proximo_horario(
            agora_local, perfil.lembretes_por_dia, perfil.janela_inicio, perfil.janela_fim
        )
        await bloq(
            repo.salvar_perfil,
            perfil.model_copy(update={"proximo_lembrete": novo.astimezone(UTC)}),
        )
