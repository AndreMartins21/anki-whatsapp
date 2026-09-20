"""Simulador de terminal: a conversa inteira, sem WhatsApp (seção 9, M6).

    python -m sim [--real-llm] [--modo guiado|producao_primeiro] [--nivel B1-B2]

Usa `ConsoleChannel` e `MemoryRepository` (nada é gravado; ao sair, tudo some), e o mesmo
`Router` do bot. Sem `--real-llm`, as respostas de IA são fabricadas (`SimTutor`); com ele, usa o
Gemini com as credenciais locais do Google (`gcloud auth application-default login`), lendo
GCP_PROJECT_ID e GEMINI_MODEL do ambiente (`make sim` carrega o `.env`). `/exportar` grava o
arquivo do Anki em `exports/`. Digite `sair` para terminar.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from app.channel.console import ConsoleChannel
from app.domain.models import NivelUsuario
from app.flows.conversa import Conversa
from app.flows.router import Router
from app.repo.memory import MemoryRepository
from app.services.anki import ExportadorAnki
from app.services.llm import LLMError, Tutor, tutor_do_ambiente
from app.services.storage import ArmazenamentoLocal
from sim.tutor import SimTutor

CHAT_DO_SIMULADOR = "simulador@c.us"
_SAIDAS = {"sair", "exit", "quit", ":q"}


async def _status_do_simulador() -> str:
    return "SIMULADOR"


async def _sem_espera(_: float) -> None:
    return None


async def _conversar(
    router: Router, entrada: Callable[[str], str], saida: Callable[[str], None]
) -> None:
    saida("Simulador do vocabot — mande uma palavra em inglês, /ajuda ou 'sair'.\n")
    while True:
        try:
            texto = await asyncio.to_thread(entrada, "você> ")
        except EOFError:
            return
        texto = texto.strip()
        if texto.lower() in _SAIDAS:
            return
        if texto:
            await router.processar(texto)


def main(
    argv: Sequence[str] | None = None,
    *,
    entrada: Callable[[str], str] = input,
    saida: Callable[[str], None] = print,
    env: Mapping[str, str] | None = None,
    exports: Path = Path("exports"),
) -> int:
    parser = argparse.ArgumentParser(prog="python -m sim", description=__doc__)
    parser.add_argument("--real-llm", action="store_true", help="usa o Gemini de verdade")
    parser.add_argument(
        "--provider", choices=["vertex_gemini", "anthropic"], default="vertex_gemini"
    )
    parser.add_argument("--model", help="ID do modelo (com --real-llm)")
    parser.add_argument("--modo", choices=["guiado", "producao_primeiro"], default="guiado")
    parser.add_argument("--nivel", choices=["A2-B1", "B1-B2", "B2-C1"], default="B1-B2")
    parser.add_argument(
        "--atraso", action="store_true", help="mantém a espera de 1-2 s antes de cada resposta"
    )
    args = parser.parse_args(argv)

    tutor: Tutor = SimTutor()
    if args.real_llm:
        try:
            tutor, _ = tutor_do_ambiente(
                args.provider, args.model, os.environ if env is None else env
            )
        except LLMError as erro:
            print(f"erro de configuração: {erro}", file=sys.stderr)
            return 2

    repo = MemoryRepository()
    conversa = (
        Conversa(ConsoleChannel(saida), CHAT_DO_SIMULADOR)
        if args.atraso
        else Conversa(ConsoleChannel(saida), CHAT_DO_SIMULADOR, dormir=_sem_espera)
    )
    nivel: NivelUsuario = args.nivel
    router = Router(
        repo=repo,
        tutor=tutor,
        conversa=conversa,
        nivel_padrao=nivel,
        modo=args.modo,
        status_da_sessao=_status_do_simulador,
        exportador=ExportadorAnki(repo, ArmazenamentoLocal(exports)),
    )
    asyncio.run(_conversar(router, entrada, saida))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
