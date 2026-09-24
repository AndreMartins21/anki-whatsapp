"""FakeChannel (seção 8.4): dublê em memória, para testes — nunca faz chamada de rede."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field


@dataclass
class FakeChannel:
    textos_enviados: list[tuple[str, str]] = field(default_factory=list)
    arquivos_enviados: list[tuple[str, str, bytes, str]] = field(default_factory=list)
    falha_no_arquivo: bool = False
    vistos: list[str] = field(default_factory=list)
    digitando: list[tuple[str, bool]] = field(default_factory=list)
    lids_conhecidos: dict[str, str | None] = field(default_factory=dict)
    mencoes_enviadas: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)
    participantes_de_grupos: dict[str, list[str]] = field(default_factory=dict)
    grupos_deixados: list[str] = field(default_factory=list)
    nomes_de_grupos: dict[str, str] = field(default_factory=dict)

    async def send_text(
        self, chat_id: str, text: str, mentions: Sequence[str] | None = None
    ) -> None:
        self.textos_enviados.append((chat_id, text))
        if mentions:
            self.mencoes_enviadas.append((chat_id, tuple(mentions)))

    async def send_file(
        self,
        chat_id: str,
        nome: str,
        conteudo: bytes,
        tipo: str,  # noqa: ARG002
        legenda: str = "",
    ) -> None:
        if self.falha_no_arquivo:
            raise RuntimeError("falha simulada ao enviar o arquivo")
        self.arquivos_enviados.append((chat_id, nome, conteudo, legenda))

    async def send_seen(self, chat_id: str) -> None:
        self.vistos.append(chat_id)

    async def typing(self, chat_id: str, on: bool) -> None:
        self.digitando.append((chat_id, on))

    async def leave_group(self, chat_id: str) -> None:
        self.grupos_deixados.append(chat_id)

    async def group_participants(self, chat_id: str) -> list[str]:
        return list(self.participantes_de_grupos.get(chat_id, []))

    async def group_name(self, chat_id: str) -> str | None:
        return self.nomes_de_grupos.get(chat_id)

    async def resolve_lid(self, lid: str) -> str | None:
        return self.lids_conhecidos.get(lid)
