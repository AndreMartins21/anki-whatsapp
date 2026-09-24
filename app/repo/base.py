"""Interface de persistência (seção 7.1 da spec, ADR-0003, ADR-0017).

Duas peças: o `Banco` (a raiz: deduplicação do webhook, cache de LIDs e a lista dos espaços) e o
`Repository`, o caderno de UM espaço (um chat privado ou um grupo), que o banco entrega em
`do_espaco`. Os fluxos só conhecem o `Repository`, então não sabem quantos espaços existem.

Síncrona de propósito: a lógica de negócio é síncrona e roda em threadpool (seção 8.1); o
cliente do Firestore também é síncrono.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol

from app.domain.models import Entry, Profile, Sentence, Sessao, StatusEntrada, slugify

PROCESSED_TTL = timedelta(days=7)
# Espaço com lembretes ligados e ainda sem próximo horário: "vencido desde sempre", para o
# agendador calcular o primeiro horário no próximo tick.
SEM_HORARIO_AINDA = datetime(1970, 1, 1, tzinfo=UTC)
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

    def apagar_tudo(self) -> None:
        """Apaga o espaço inteiro: perfil, sessão, entradas e frases."""
        ...


class Banco(Protocol):
    def do_espaco(self, espaco_id: str) -> Repository:
        """O caderno do espaço (`NUMERO@c.us` no privado, `...@g.us` no grupo). Nada é lido nem
        gravado até o primeiro uso, e um espaço nunca enxerga os dados de outro."""
        ...

    def listar_espacos_com_lembrete(self, agora: datetime) -> list[str]:
        """Espaços com lembretes ligados e destino conhecido cujo próximo horário já chegou (ou
        ainda não foi calculado). Uma consulta só por tick do agendador, sem ler os demais."""
        ...

    def marcar_processada(self, message_id: str, agora: datetime) -> bool:
        """Deduplicação do webhook: `True` na primeira vez que vê o id, `False` depois."""
        ...

    def obter_numero_do_lid(self, lid: str) -> str | None: ...

    def salvar_numero_do_lid(self, lid: str, numero: str) -> None: ...


def tipo_do_espaco(espaco_id: str) -> str:
    return "grupo" if espaco_id.endswith("@g.us") else "privado"


def proximo_tick(perfil: Profile) -> datetime | None:
    """O que o `Banco` espelha do perfil no documento do espaço para a consulta dos lembretes:
    quando o agendador deve olhar este espaço de novo, ou `None` se ele não deve olhar nunca."""
    if perfil.lembretes_por_dia == 0 or perfil.chat_id is None:
        return None
    return perfil.proximo_lembrete or SEM_HORARIO_AINDA


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
