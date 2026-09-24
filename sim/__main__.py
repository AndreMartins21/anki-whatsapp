"""Simulador de terminal: a conversa inteira, sem WhatsApp (seção 9, M6).

    python -m sim [--real-llm] [--letras-reais] [--nivel B1-B2]
    python -m sim --grupo [--professor NOME]...

Com `--grupo` (M16), simula um grupo de turma com vários participantes: cada linha é
`nome: mensagem` (ex.: `ana: !add stall`). Só as linhas que começam com o prefixo (`!`) chegam ao
bot; as outras aparecem como ignoradas, como no WhatsApp real. O participante `dono` é o dono do
bot (pode usar `!teacher`); `--professor NOME` cadastra professores de saída.

Usa `ConsoleChannel` e `MemoryRepository` (nada é gravado; ao sair, tudo some), e o mesmo
`Router` do bot. Sem `--real-llm`, as respostas de IA são fabricadas (`SimTutor`); com ele, usa o
Gemini com as credenciais locais do Google (`gcloud auth application-default login`), lendo
GCP_PROJECT_ID e GEMINI_MODEL do ambiente (`make sim` carrega o `.env`). `/exportar` grava o
planilha Excel em `exports/`. `/song paper plane` pratica com uma música inventada (com
`--letras-reais`, busca no LRCLIB de verdade). Digite `sair` para terminar.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import zlib
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from app.channel.console import ConsoleChannel
from app.domain.models import Membro, NivelUsuario, agora_utc
from app.flows import grupo as flows_grupo
from app.flows.base import Autor
from app.flows.conversa import Conversa
from app.flows.router import Router
from app.repo.memory import MemoryBanco
from app.services.letras import LrclibProvider, LyricsProvider
from app.services.llm import LLMError, Tutor, tutor_do_ambiente
from app.services.planilha import ExportadorExcel
from app.services.storage import ArmazenamentoLocal
from sim.letras import letras_do_simulador
from sim.tutor import SimTutor

CHAT_DO_SIMULADOR = "simulador@c.us"
GRUPO_DO_SIMULADOR = "120363000000000001@g.us"
PREFIXO_DO_SIMULADOR = "!"
NOME_DO_DONO = "dono"
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
            await router.processar(texto, CHAT_DO_SIMULADOR)


def numero_do_participante(nome: str) -> str:
    """Um número de mentira e estável para cada nome (o simulador não tem WhatsApp)."""
    if nome == NOME_DO_DONO:
        return "5531990000000"
    return "55319" + f"{zlib.crc32(nome.encode()) % 10**8:08d}"


async def _conversar_no_grupo(
    router: Router, entrada: Callable[[str], str], saida: Callable[[str], None]
) -> None:
    saida(
        "Simulador do grupo — uma linha por mensagem: `nome: mensagem` (ex.: `ana: !add stall`).\n"
        f"Só o que começa com {PREFIXO_DO_SIMULADOR} chega ao bot. Digite 'sair' para terminar.\n"
    )
    while True:
        try:
            linha = await asyncio.to_thread(entrada, "grupo> ")
        except EOFError:
            return
        linha = linha.strip()
        if linha.lower() in _SAIDAS:
            return
        if not linha:
            continue
        nome, separador, texto = linha.partition(":")
        if not separador or not nome.strip() or not texto.strip():
            saida("  (use `nome: mensagem`)")
            continue
        nome, texto = nome.strip(), texto.strip()
        saida(f"[{nome}] {texto}")
        if flows_grupo.sem_prefixo(texto, PREFIXO_DO_SIMULADOR) is None:
            saida("  (ignorado: sem prefixo, o bot não lê)")
            continue
        autor = Autor(numero_do_participante(nome), nome)
        await router.processar(texto, GRUPO_DO_SIMULADOR, autor)


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
    parser.add_argument(
        "--letras-reais", action="store_true", help="busca as letras do /song no LRCLIB"
    )
    parser.add_argument("--nivel", choices=["A2-B1", "B1-B2", "B2-C1"], default="B1-B2")
    parser.add_argument(
        "--grupo", action="store_true", help="simula um grupo de turma (`nome: mensagem`)"
    )
    parser.add_argument(
        "--professor", action="append", default=[], help="cadastra um professor (com --grupo)"
    )
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

    banco = MemoryBanco()
    canal = ConsoleChannel(saida, exports)

    def criar_conversa(chat_id: str) -> Conversa:
        if args.atraso:
            return Conversa(canal, chat_id)
        return Conversa(canal, chat_id, dormir=_sem_espera)

    nivel: NivelUsuario = args.nivel
    letras: LyricsProvider = LrclibProvider() if args.letras_reais else letras_do_simulador()
    router = Router(
        banco=banco,
        tutor=tutor,
        criar_conversa=criar_conversa,
        nivel_padrao=nivel,
        status_da_sessao=_status_do_simulador,
        exportador=ExportadorExcel(ArmazenamentoLocal(exports)),
        letras=letras,
        prefixo_do_grupo=PREFIXO_DO_SIMULADOR,
        eh_dono=lambda numero: numero == numero_do_participante(NOME_DO_DONO),
    )
    if args.grupo:
        espaco = banco.do_espaco(GRUPO_DO_SIMULADOR)
        for nome in args.professor:
            espaco.salvar_membro(
                numero_do_participante(nome),
                Membro(papel="professor", nome=nome, entrou_em=agora_utc()),
            )
        asyncio.run(_conversar_no_grupo(router, entrada, saida))
        return 0
    asyncio.run(_conversar(router, entrada, saida))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
