"""Migra o formato de um usuário só (`profile/me`, `session/current`, `entries/...` na RAIZ do
Firestore) para o espaço do dono: `espacos/{chat_id}/...` (M14, ADR-0017).

    python -m scripts.migrar_multiusuario --projeto ID [--espaco CHAT | --dono NUMERO]
    python -m scripts.migrar_multiusuario --projeto ID ... --executar
    python -m scripts.migrar_multiusuario --projeto ID ... --limpar-origem

- O padrão é **dry run**: mostra o que copiaria e não escreve nada. Copiar de verdade exige
  `--executar`.
- Idempotente: entrada nova é copiada; entrada existente só é sobrescrita se a origem for mais nova
  (o bot antigo ainda gravou depois da última cópia); frases se comparam por `(texto, criado_em)` e
  nunca duplicam; o perfil só é copiado se o destino ainda não tiver um.
- Não apaga a origem. `--limpar-origem` é um segundo comando e só roda com a cópia completa.
- Roda na máquina local, com as credenciais padrão (ADC), não na VM: o Dockerfile só leva `app/`.
- O espaço é o `chat_id` real que o WhatsApp informa, guardado no `profile/me` antigo (a conta pode
  estar sem o nono dígito). Sem perfil, cai em `--dono` (ou a variável OWNER_NUMBER).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.models import Entry, Estado, Sentence
from app.repo.base import Repository


class CopiaIncompleta(Exception):
    """`--limpar-origem` com algo da origem que ainda não está no destino."""


@dataclass
class Relatorio:
    perfil: bool = False
    sessao: bool = False
    entradas_novas: int = 0
    entradas_atualizadas: int = 0
    entradas_iguais: int = 0
    frases_copiadas: int = 0


def _chave(frase: Sentence) -> tuple[str, object]:
    return (frase.texto, frase.criado_em)


def migrar(origem: Repository, destino: Repository, *, executar: bool) -> Relatorio:
    relatorio = Relatorio()

    perfil = origem.obter_perfil()
    if perfil is not None and destino.obter_perfil() is None:
        relatorio.perfil = True
        if executar:
            destino.salvar_perfil(perfil)

    sessao = origem.obter_sessao()
    if sessao.estado != Estado.IDLE and destino.obter_sessao().estado == Estado.IDLE:
        relatorio.sessao = True
        if executar:
            destino.salvar_sessao(sessao)

    for entrada in origem.listar_entradas():
        existente = destino.obter_entrada(entrada.slug)
        if existente is None:
            relatorio.entradas_novas += 1
            if executar:
                destino.criar_entrada(entrada)
        elif entrada.atualizado_em > existente.atualizado_em:
            relatorio.entradas_atualizadas += 1
            if executar:
                destino.salvar_entrada(entrada)
        else:
            relatorio.entradas_iguais += 1

        ja_no_destino = {_chave(f) for f in destino.listar_frases(entrada.slug)}
        for frase in origem.listar_frases(entrada.slug):
            if _chave(frase) not in ja_no_destino:
                relatorio.frases_copiadas += 1
                if executar:
                    destino.adicionar_frase(entrada.slug, frase)
    return relatorio


def _entrada_esta_no_destino(entrada: Entry, destino: Repository) -> bool:
    copiada = destino.obter_entrada(entrada.slug)
    return copiada is not None and copiada.atualizado_em >= entrada.atualizado_em


def copia_completa(origem: Repository, destino: Repository) -> bool:
    if origem.obter_perfil() is not None and destino.obter_perfil() is None:
        return False
    for entrada in origem.listar_entradas():
        if not _entrada_esta_no_destino(entrada, destino):
            return False
        no_destino = {_chave(f) for f in destino.listar_frases(entrada.slug)}
        if any(_chave(f) not in no_destino for f in origem.listar_frases(entrada.slug)):
            return False
    return True


def limpar_origem(origem: Repository, destino: Repository) -> None:
    if origem.obter_perfil() is None and not origem.listar_entradas():
        return  # já limpa (ou nunca teve nada): nada a apagar
    if not copia_completa(origem, destino):
        raise CopiaIncompleta("há dados na origem que ainda não estão no destino")
    origem.apagar_tudo()


def escolher_espaco(origem: Repository, *, espaco: str | None, dono: str | None) -> str:
    if espaco:
        return espaco
    perfil = origem.obter_perfil()
    if perfil is not None and perfil.chat_id:
        return perfil.chat_id
    digitos = re.sub(r"\D", "", dono or "")
    if not digitos:
        raise ValueError("sem perfil antigo e sem número do dono: informe --dono ou --espaco")
    return f"{digitos}@c.us"


def _argumentos(argv: Sequence[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--projeto", required=True, help="ID do projeto GCP (o do Firestore)")
    ap.add_argument("--espaco", help="chat id do espaço de destino (padrão: chat_id do perfil)")
    ap.add_argument("--dono", default=os.environ.get("OWNER_NUMBER"), help="número do dono")
    grupo = ap.add_mutually_exclusive_group()
    grupo.add_argument("--executar", action="store_true", help="copia de verdade (padrão: dry run)")
    grupo.add_argument(
        "--limpar-origem", action="store_true", help="apaga a origem (cópia completa)"
    )
    return ap.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _argumentos(argv)

    from google.cloud import firestore

    from app.repo.firestore import FirestoreBanco, FirestoreRepository

    cliente = firestore.Client(project=args.projeto)
    origem = FirestoreRepository(cliente)
    try:
        espaco = escolher_espaco(origem, espaco=args.espaco, dono=args.dono)
    except ValueError as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return 2
    destino = FirestoreBanco(cliente).do_espaco(espaco)
    print(f"projeto: {args.projeto}\nespaço de destino: espacos/{espaco[:6]}…")

    if args.limpar_origem:
        try:
            limpar_origem(origem, destino)
        except CopiaIncompleta as erro:
            print(f"recusado: {erro}. Rode --executar de novo e confira.", file=sys.stderr)
            return 1
        print("origem apagada.")
        return 0

    relatorio = migrar(origem, destino, executar=args.executar)
    modo = "COPIADO" if args.executar else "DRY RUN (nada foi escrito; use --executar)"
    print(
        f"{modo}: perfil={relatorio.perfil} sessão={relatorio.sessao} "
        f"entradas novas={relatorio.entradas_novas} atualizadas={relatorio.entradas_atualizadas} "
        f"iguais={relatorio.entradas_iguais} frases={relatorio.frases_copiadas}"
    )
    if args.executar:
        print(f"cópia completa: {copia_completa(origem, destino)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
