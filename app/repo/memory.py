"""MemoryBanco / MemoryRepository: implementação em memória, para testes e para o simulador
(`make sim`).

Guarda cópias, como um banco de verdade: alterar o objeto que você passou (ou recebeu) depois de
salvar não muda o que está guardado.
"""

from __future__ import annotations

from datetime import datetime

from app.domain.models import Entry, Profile, Sentence, Sessao, StatusEntrada
from app.repo.base import EntradaJaExiste, GrupoAtivo, Repository, proximo_tick


class MemoryRepository:
    """O caderno de um espaço. Sozinho (`MemoryRepository()`) serve de origem dos scripts."""

    def __init__(self) -> None:
        self._perfil: Profile | None = None
        self._sessao: Sessao | None = None
        self._entradas: dict[str, Entry] = {}
        self._frases: dict[str, list[Sentence]] = {}

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

    def apagar_tudo(self) -> None:
        self._perfil = None
        self._sessao = None
        self._entradas.clear()
        self._frases.clear()


class MemoryBanco:
    def __init__(self) -> None:
        self._espacos: dict[str, MemoryRepository] = {}
        self._processadas: set[str] = set()
        self._lids: dict[str, str] = {}
        self._admins: dict[str, datetime] = {}
        self._grupos_ativos: dict[str, GrupoAtivo] = {}
        self._pendentes: dict[str, datetime] = {}

    def do_espaco(self, espaco_id: str) -> Repository:
        return self._espacos.setdefault(espaco_id, MemoryRepository())

    def listar_espacos_com_lembrete(self, agora: datetime) -> list[str]:
        vencidos: list[str] = []
        for espaco_id, repo in self._espacos.items():
            perfil = repo.obter_perfil()
            tick = proximo_tick(perfil) if perfil else None
            if tick is not None and tick <= agora:
                vencidos.append(espaco_id)
        return vencidos

    def marcar_processada(self, message_id: str, agora: datetime) -> bool:  # noqa: ARG002
        if message_id in self._processadas:
            return False
        self._processadas.add(message_id)
        return True

    def obter_numero_do_lid(self, lid: str) -> str | None:
        return self._lids.get(lid)

    def salvar_numero_do_lid(self, lid: str, numero: str) -> None:
        self._lids[lid] = numero

    def listar_admins(self) -> list[str]:
        return [n for n, _ in sorted(self._admins.items(), key=lambda par: par[1])]

    def adicionar_admin(self, numero: str, *, por: str, agora: datetime) -> bool:  # noqa: ARG002
        if numero in self._admins:
            return False
        self._admins[numero] = agora
        return True

    def remover_admin(self, numero: str) -> bool:
        return self._admins.pop(numero, None) is not None

    def grupo_esta_ativo(self, grupo_id: str) -> bool:
        return grupo_id in self._grupos_ativos

    def ativar_grupo(self, grupo_id: str, *, nome: str | None, por: str, agora: datetime) -> None:
        self._grupos_ativos[grupo_id] = GrupoAtivo(grupo_id, nome, por, agora)
        self._pendentes.pop(grupo_id, None)

    def desativar_grupo(self, grupo_id: str) -> bool:
        return self._grupos_ativos.pop(grupo_id, None) is not None

    def listar_grupos_ativos(self) -> list[GrupoAtivo]:
        return sorted(self._grupos_ativos.values(), key=lambda g: (g.ativado_em, g.id))

    def registrar_grupo_pendente(self, grupo_id: str, agora: datetime) -> bool:
        if grupo_id in self._pendentes:
            return False
        self._pendentes[grupo_id] = agora
        return True

    def listar_grupos_pendentes(self) -> list[tuple[str, datetime]]:
        return sorted(self._pendentes.items(), key=lambda par: (par[1], par[0]))

    def remover_grupo_pendente(self, grupo_id: str) -> None:
        self._pendentes.pop(grupo_id, None)
