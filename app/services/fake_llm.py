"""Dublês de IA: `FakeLLMProvider` (testa `LLMTutor`) e `FakeTutor` (testa os fluxos), sem rede nem custo."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from pydantic import BaseModel

from app.domain.models import (
    Evaluation,
    Expansion,
    Explanation,
    NivelUsuario,
    Sense,
    SentidoSalvo,
)


@dataclass(frozen=True)
class ChamadaLLM:
    sistema: str
    usuario: str
    schema: type[BaseModel]
    modelo: str
    temperatura: float


@dataclass
class FakeLLMProvider:
    """Cada chamada consome a próxima resposta da fila: um modelo Pydantic (vira JSON), um texto
    cru (para simular JSON inválido) ou uma exceção (para simular falha do provedor)."""

    respostas: list[BaseModel | str | Exception]
    chamadas: list[ChamadaLLM] = field(default_factory=list)

    def gerar(
        self,
        *,
        sistema: str,
        usuario: str,
        schema: type[BaseModel],
        modelo: str,
        temperatura: float,
    ) -> str:
        self.chamadas.append(ChamadaLLM(sistema, usuario, schema, modelo, temperatura))
        resposta = self.respostas.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        if isinstance(resposta, BaseModel):
            return resposta.model_dump_json()
        return resposta


@dataclass
class FakeTutor:
    """Dublê do `Tutor` (nível de negócio) para testar fluxos: cada método consome a próxima
    resposta da sua fila; uma exceção na fila é levantada. `chamadas` guarda (método, argumentos)."""

    explicacoes: list[Explanation | Exception] = field(default_factory=list)
    avaliacoes: list[Evaluation | Exception] = field(default_factory=list)
    exemplos: list[list[str] | Exception] = field(default_factory=list)
    expansoes: list[list[Expansion] | Exception] = field(default_factory=list)
    chamadas: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)

    def _proxima[T](self, fila: list[T | Exception]) -> T:
        resposta = fila.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta

    def explain(self, texto: str, nivel: NivelUsuario) -> Explanation:
        self.chamadas.append(("explain", (texto, nivel)))
        return self._proxima(self.explicacoes)

    def evaluate(
        self, palavra: str, sentido: SentidoSalvo | Sense, frase: str, nivel: NivelUsuario
    ) -> Evaluation:
        self.chamadas.append(("evaluate", (palavra, sentido.traducao, frase, nivel)))
        return self._proxima(self.avaliacoes)

    def examples(
        self, palavra: str, sentido: SentidoSalvo | Sense, nivel: NivelUsuario, n: int = 3
    ) -> list[str]:
        self.chamadas.append(("examples", (palavra, sentido.traducao, nivel, n)))
        return self._proxima(self.exemplos)

    def expansions(
        self,
        palavra: str,
        sentido: SentidoSalvo | Sense,
        nivel: NivelUsuario,
        ja_existentes: Sequence[str],
    ) -> list[Expansion]:
        self.chamadas.append(
            ("expansions", (palavra, sentido.traducao, nivel, tuple(ja_existentes)))
        )
        return self._proxima(self.expansoes)
