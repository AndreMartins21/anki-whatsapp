"""MemoryRepository: implementação em memória, para testes e para o simulador (`make sim`).

Guarda cópias, como um banco de verdade: alterar o objeto que você passou (ou recebeu) depois de
salvar não muda o que está guardado.
"""

from __future__ import annotations

from datetime import datetime

from app.domain.models import Entry, Profile, Sentence, Sessao, StatusEntrada
from app.repo.base import EntradaJaExiste


class MemoryRepository:
    def __init__(self) -> None:
        self._perfil: Profile | None = None
        self._sessao: Sessao | None = None
        self._entradas: dict[str, Entry] = {}
        self._frases: dict[str, list[Sentence]] = {}
        self._processadas: set[str] = set()
        self._lids: dict[str, str] = {}

    def obter_perfil(self) -> Profile | None:
        return self._perfil.model_copy(deep=True) if self._perfil else None

    def salvar_perfil(self, perfil: Profile) -> None:
        self._perfil = perfil.model_copy(deep=True)

    def obter_sessao(self) -> Sessao:
        return self._sessao.model_copy(deep=True) if self._sessao else Sessao()

    def salvar_sessao(self, sessao: Sessao) -> None:
        self._sessao = sessao.model_copy(deep=True)

    def obter_entrada(self, slug: str) -> Entry | None:
        entrada = self._entradas.get(slug)
        return entrada.model_copy(deep=True) if entrada else None

    def criar_entrada(self, entrada: Entry) -> None:
        if entrada.slug in self._entradas:
            raise EntradaJaExiste(entrada.slug)
        self._entradas[entrada.slug] = entrada.model_copy(deep=True)

    def salvar_entrada(self, entrada: Entry) -> None:
        self._entradas[entrada.slug] = entrada.model_copy(deep=True)

    def listar_entradas(self, status: StatusEntrada | None = None) -> list[Entry]:
        entradas = [e for e in self._entradas.values() if status is None or e.status == status]
        entradas.sort(key=lambda e: (e.criado_em, e.slug))
        return [e.model_copy(deep=True) for e in entradas]

    def apagar_entrada(self, slug: str) -> bool:
        existia = self._entradas.pop(slug, None) is not None
        self._frases.pop(slug, None)
        return existia

    def adicionar_frase(self, slug: str, frase: Sentence) -> None:
        self._frases.setdefault(slug, []).append(frase.model_copy(deep=True))

    def listar_frases(self, slug: str) -> list[Sentence]:
        frases = sorted(self._frases.get(slug, []), key=lambda f: f.criado_em)
        return [f.model_copy(deep=True) for f in frases]

    def marcar_processada(self, message_id: str, agora: datetime) -> bool:  # noqa: ARG002
        if message_id in self._processadas:
            return False
        self._processadas.add(message_id)
        return True

    def obter_numero_do_lid(self, lid: str) -> str | None:
        return self._lids.get(lid)

    def salvar_numero_do_lid(self, lid: str, numero: str) -> None:
        self._lids[lid] = numero
