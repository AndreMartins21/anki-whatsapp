"""Interface de persistência (seção 7.1 da spec, ADR-0003).

Síncrona de propósito: a lógica de negócio é síncrona e roda em threadpool (seção 8.1); o
cliente do Firestore também é síncrono.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol

from app.domain.models import Entry, Profile, Sentence, Sessao, StatusEntrada, slugify

PROCESSED_TTL = timedelta(days=7)
_MAX_SLUGS_POR_PALAVRA = 50


class EntradaJaExiste(Exception):
    """`criar_entrada` com um slug que já está no banco."""


class Repository(Protocol):
    def obter_perfil(self) -> Profile | None: ...

    def salvar_perfil(self, perfil: Profile) -> None: ...

    def obter_sessao(self) -> Sessao:
        """A sessão atual; sem documento ainda, uma sessão nova em `IDLE`."""
        ...

    def salvar_sessao(self, sessao: Sessao) -> None: ...

    def obter_entrada(self, slug: str) -> Entry | None: ...

    def criar_entrada(self, entrada: Entry) -> None:
        """Falha com `EntradaJaExiste` se o slug já existe (semântica de `create()`)."""
        ...

    def salvar_entrada(self, entrada: Entry) -> None:
        """Grava por cima (atualização)."""
        ...

    def listar_entradas(self, status: StatusEntrada | None = None) -> list[Entry]:
        """Em ordem de criação; `status` opcional filtra."""
        ...

    def apagar_entrada(self, slug: str) -> bool:
        """Apaga a entrada e suas frases; `False` se ela não existia."""
        ...

    def adicionar_frase(self, slug: str, frase: Sentence) -> None: ...

    def listar_frases(self, slug: str) -> list[Sentence]:
        """Em ordem de criação."""
        ...

    def marcar_processada(self, message_id: str, agora: datetime) -> bool:
        """Deduplicação do webhook: `True` na primeira vez que vê o id, `False` depois."""
        ...

    def obter_numero_do_lid(self, lid: str) -> str | None: ...

    def salvar_numero_do_lid(self, lid: str, numero: str) -> None: ...


def resolver_slug(repo: Repository, palavra: str, traducao_do_sentido: str) -> str:
    """`slug` livre para a palavra (seção 7.1): o da própria palavra, o mesmo se o sentido já
    é o que está salvo, ou `--s2`, `--s3`... quando a palavra existe com outro sentido."""
    base = slugify(palavra)
    for numero in range(1, _MAX_SLUGS_POR_PALAVRA + 1):
        candidato = base if numero == 1 else f"{base}--s{numero}"
        existente = repo.obter_entrada(candidato)
        if existente is None or existente.sentido.traducao == traducao_do_sentido:
            return candidato
    raise RuntimeError(f"palavras demais com o slug {base!r}")
