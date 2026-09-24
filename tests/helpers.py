"""Montagem compartilhada dos testes de fluxo: roteador com fakes, relógio controlável e as
respostas de IA do ciclo "stall" (M9: interface em inglês, menu único)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.channel.fake import FakeChannel
from app.domain.models import (
    Evaluation,
    Expansion,
    Explanation,
    Sense,
)
from app.flows.commands import Exportador, StatusDaSessao
from app.flows.conversa import Conversa
from app.flows.router import Router
from app.repo.memory import MemoryRepository
from app.services.fake_llm import FakeTutor
from app.services.letras import LyricsProvider

CHAT = "5531999998888@c.us"
T0 = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)

S1 = Sense(
    id="s1",
    traducao="travar, emperrar",
    definicao="to stop making progress",
    exemplo="The [[talks]] stalled.",
)
S2 = Sense(
    id="s2",
    traducao="enrolar",
    definicao="to delay on purpose",
    exemplo="Stop [[stalling]] and answer me.",
)


def explicacao_stall(*, sentido_do_contexto: str = "s1", dois_sentidos: bool = True) -> Explanation:
    return Explanation(
        ok=True,
        palavra="stall",
        classe="verb",
        cefr_estimado="B2",
        sentidos=[S1, S2] if dois_sentidos else [S1],
        sentido_do_contexto=sentido_do_contexto,
        frase_contexto="The talks [[stalled]].",
        nota='"the car stalled" = the car died',
        tags=["trabalho"],
    )


def avaliacao(veredito: str = "quase") -> Evaluation:
    return Evaluation(
        usa_palavra_alvo=True,
        sentido_correto=True,
        veredito=veredito,
        correcoes=["didn't sent → didn't send"],
        versao_natural="The project [[stalled]] because the client didn't send the documents.",
        explicacao='After "didn\'t", the verb stays in the base form.',
    )


def expansoes() -> list[Expansion]:
    return [
        Expansion(expressao="stall for time", traducao="enrolar", tipo="colocacao"),
        Expansion(expressao="stall out", traducao="pifar", tipo="phrasal_verb"),
        Expansion(expressao="stalled talks", traducao="negociações paradas", tipo="colocacao"),
        Expansion(expressao="grind to a halt", traducao="parar aos poucos", tipo="expressao"),
    ]


class Relogio:
    def __init__(self) -> None:
        self.agora_ = T0

    def agora(self) -> datetime:
        return self.agora_

    def avancar(self, delta: timedelta) -> None:
        self.agora_ += delta


@dataclass
class Montagem:
    router: Router
    channel: FakeChannel
    repo: MemoryRepository
    tutor: FakeTutor
    relogio: Relogio
    conversa: Conversa
    esperas: list[float] = field(default_factory=list)

    async def diz(self, texto: str) -> list[str]:
        """Manda `texto` como o aluno e devolve o que o bot respondeu (só os textos)."""
        antes = len(self.channel.textos_enviados)
        await self.router.processar(texto)
        return [t for _, t in self.channel.textos_enviados[antes:]]


def montar(
    *,
    tutor: FakeTutor | None = None,
    exportador: Exportador | None = None,
    status_da_sessao: StatusDaSessao | None = None,
    letras: LyricsProvider | None = None,
) -> Montagem:
    channel = FakeChannel()
    repo = MemoryRepository()
    tutor = tutor or FakeTutor()
    relogio = Relogio()
    esperas: list[float] = []

    async def dormir(segundos: float) -> None:
        esperas.append(segundos)

    conversa = Conversa(channel, CHAT, dormir=dormir, atraso=lambda: 1.5)
    router = Router(
        repo=repo,
        tutor=tutor,
        conversa=conversa,
        nivel_padrao="B1-B2",
        agora=relogio.agora,
        status_da_sessao=status_da_sessao,
        exportador=exportador,
        letras=letras,
    )
    return Montagem(router, channel, repo, tutor, relogio, conversa, esperas)
