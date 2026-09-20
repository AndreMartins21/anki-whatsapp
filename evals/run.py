"""Mede a taxa de acerto da avaliação de frases contra a API real (fora do pytest, seção 6).

    python -m evals.run [--provider vertex_gemini|anthropic] [--model ID]

Lê a configuração do ambiente (`make evals` carrega o `.env` antes): no Vertex AI, `GCP_PROJECT_ID`
(+ `VERTEX_LOCATION`, padrão `global`) e as credenciais locais (`gcloud auth application-default
login`); na Anthropic, `ANTHROPIC_API_KEY`. Nenhuma chave é impressa. Cada execução chama a API de
verdade e custa centavos — serve para comparar modelos antes de escolher `GEMINI_MODEL`.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from app.domain.models import NivelUsuario, SentidoSalvo, Veredito
from app.services.llm import LLMError, Tutor, tutor_do_ambiente

CAMINHO_PADRAO = Path(__file__).parent / "sentencas.yaml"


ErroDeConfiguracao = LLMError  # falta algo no ambiente para rodar contra a API


class Caso(BaseModel):
    id: str
    palavra: str
    sentido: SentidoSalvo
    frase: str
    esperado: list[Veredito] = Field(min_length=1)


@dataclass(frozen=True)
class Resultado:
    caso: Caso
    obtido: Veredito | None
    erro: str | None
    segundos: float

    @property
    def acertou(self) -> bool:
        return self.obtido is not None and self.obtido in self.caso.esperado


@dataclass(frozen=True)
class Relatorio:
    resultados: list[Resultado]

    @property
    def acertos(self) -> int:
        return sum(r.acertou for r in self.resultados)

    @property
    def erros(self) -> int:
        return sum(r.erro is not None for r in self.resultados)

    @property
    def taxa(self) -> float:
        return self.acertos / len(self.resultados) if self.resultados else 0.0


def carregar_casos(caminho: Path) -> list[Caso]:
    bruto = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    return [Caso.model_validate(item) for item in bruto]


def avaliar(tutor: Tutor, casos: Sequence[Caso], nivel: NivelUsuario) -> Relatorio:
    resultados: list[Resultado] = []
    for caso in casos:
        inicio = time.perf_counter()
        obtido: Veredito | None = None
        erro: str | None = None
        try:
            obtido = tutor.evaluate(caso.palavra, caso.sentido, caso.frase, nivel).veredito
        except LLMError as falha:
            erro = str(falha)
        resultados.append(Resultado(caso, obtido, erro, time.perf_counter() - inicio))
    return Relatorio(resultados)


montar_tutor = tutor_do_ambiente


def imprimir(relatorio: Relatorio, modelo: str) -> None:
    print(f"\nModelo: {modelo}\n")
    for r in relatorio.resultados:
        marca = "ok " if r.acertou else "ERR"
        obtido = r.obtido or f"(falhou: {r.erro})"
        print(
            f"  [{marca}] {r.caso.id:<28} esperado={'|'.join(r.caso.esperado):<32} obtido={obtido}"
        )

    por_categoria: dict[str, list[bool]] = defaultdict(list)
    for r in relatorio.resultados:
        por_categoria[r.caso.esperado[0]].append(r.acertou)
    print("\nPor veredito esperado (o primeiro da lista de cada caso):")
    for categoria, acertos in sorted(por_categoria.items()):
        print(f"  {categoria:<24} {sum(acertos)}/{len(acertos)}")

    total = len(relatorio.resultados)
    media = sum(r.segundos for r in relatorio.resultados) / total if total else 0.0
    print(
        f"\nAcertos: {relatorio.acertos}/{total} ({relatorio.taxa:.0%})"
        f" · falhas da IA: {relatorio.erros} · latência média: {media:.1f}s"
    )


def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.run", description=__doc__)
    parser.add_argument(
        "--provider", choices=["vertex_gemini", "anthropic"], default="vertex_gemini"
    )
    parser.add_argument("--model", help="ID do modelo (padrão: o do ambiente)")
    parser.add_argument("--nivel", choices=["A2-B1", "B1-B2", "B2-C1"], default="B1-B2")
    parser.add_argument("--casos", type=Path, default=CAMINHO_PADRAO)
    args = parser.parse_args(argv)

    try:
        tutor, modelo = montar_tutor(args.provider, args.model, os.environ if env is None else env)
    except LLMError as erro:
        print(f"erro de configuração: {erro}", file=sys.stderr)
        return 2

    imprimir(avaliar(tutor, carregar_casos(args.casos), args.nivel), modelo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
