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
from app.flows import capture, commands, freeform, grupo, practice, review, song, synonyms
from app.flows.base import FUSO_PADRAO, Autor, ConfigGrupo, Deps, bloq
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
        prefixo_do_grupo: str = "!",
        eh_dono: Callable[[str], bool] = lambda _numero: False,
        config_grupo: ConfigGrupo | None = None,
    ) -> None:
        self._banco = banco
        self._tutor = tutor
        self._criar_conversa = criar_conversa
        self._agora = agora
        self._fuso = fuso
        self._letras = letras
        self._prefixo_do_grupo = prefixo_do_grupo
        self._eh_dono = eh_dono
        self._config_grupo = config_grupo or ConfigGrupo()
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

    def _deps(self, chat_id: str, autor: Autor | None = None) -> Deps:
        return Deps(
            repo=self._banco.do_espaco(chat_id),
            tutor=self._tutor,
            conversa=self.conversa_do(chat_id),
            agora=self._agora,
            fuso=self._fuso,
            letras=self._letras,
            grupo_prefixo=self._prefixo_do_grupo if chat_id.endswith("@g.us") else None,
            autor=autor,
            chat_id=chat_id,
            grupo_cfg=self._config_grupo,
        )

    async def responder_avulso(self, chat_id: str, texto: str) -> None:
        """Uma resposta fixa (sem IA e sem mexer na sessão), com o mesmo ritmo humano e o mesmo
        limite de mensagens seguidas das demais: usado pelos comandos de admin (M15)."""
        async with self._trava(chat_id):
            conversa = self.conversa_do(chat_id)
            conversa.usuario_falou()
            await conversa.enviar(texto)

    async def midia_nao_suportada(self, chat_id: str) -> None:
        async with self._trava(chat_id):
            conversa = self.conversa_do(chat_id)
            conversa.usuario_falou()
            await conversa.enviar(messages.MIDIA_NAO_SUPORTADA)

    async def processar(self, texto: str, chat_id: str, autor: Autor | None = None) -> None:
        """`chat_id` é o espaço E o destino das respostas: o chat de onde a mensagem veio. Em
        grupo (M16) `autor` é quem escreveu e `texto` vem COM o prefixo: sem ele, é conversa
        entre pessoas e nada acontece."""
        async with self._trava(chat_id):
            d = self._deps(chat_id, autor)
            de_grupo: tuple[Autor, str] | None = None
            if d.em_grupo:
                resto = grupo.sem_prefixo(texto, d.p)
                if autor is None or resto is None:
                    return
                de_grupo = (autor, resto)
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
                if de_grupo is not None:
                    nova = await grupo.tratar(
                        d,
                        sessao,
                        perfil,
                        de_grupo[1],
                        autor=de_grupo[0],
                        conversar=self._conversar,
                        eh_dono=self._eh_dono,
                    )
                elif self._como_comando(texto).startswith("/"):
                    nova = await commands.executar(
                        d,
                        sessao,
                        perfil,
                        self._como_comando(texto),
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

    def _como_comando(self, texto: str) -> str:
        """No privado, o prefixo do grupo (`!`) é um apelido escondido da barra: `!list` vale
        `/list`. Só vale se uma letra vem logo depois; `!!!` ou `!1` seguem como texto."""
        limpo = texto.strip()
        p = self._prefixo_do_grupo
        if limpo.startswith(p) and len(limpo) > len(p) and limpo[len(p)].isalpha():
            return "/" + limpo[len(p) :]
        return limpo

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
            case Acao.PULAR:
                return await practice.pular(d)
            case Acao.IGNORAR:
                return await practice.ignorar(d, sessao)
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

    async def expirar_marcacao(self, chat_id: str, forcar: bool = False) -> None:
        """M17: chamado pelo agendador quando a pessoa marcada numa revisão em grupo não respondeu
        no prazo (`forcar` ignora o prazo, para o simulador). Sem revisão em andamento, ou já
        respondida a tempo, não faz nada. Mesma trava do resto; não conta como fala do aluno."""
        async with self._trava(chat_id):
            d = self._deps(chat_id)
            sessao = await bloq(d.repo.obter_sessao)
            prazo = sessao.marcacao_expira_em
            if Estado(sessao.estado) != Estado.REVIEWING or prazo is None:
                return
            if not forcar and prazo > d.agora():
                return
            nova = await review.sem_resposta(d, sessao)
            await bloq(d.repo.salvar_sessao, nova.model_copy(update={"atualizado_em": d.agora()}))
