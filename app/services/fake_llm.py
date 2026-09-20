"""FakeLLMProvider: respostas roteirizadas, para testar `LLMTutor` sem rede nem custo."""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel


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
