"""Firestore (ADR-0003, ADR-0017): Cloud Firestore em modo nativo, esquema da seção 7.1.

    espacos/{espaco_id}                               {tipo, criado_em, proximo_tick?}
    espacos/{espaco_id}/profile/me                    espacos/{espaco_id}/session/current
    espacos/{espaco_id}/entries/{slug}                espacos/{espaco_id}/entries/{slug}/sentences/{auto}
    processed/{message_id}                            lids/{lid}

`processed.expira_em` é o campo da política de TTL de 7 dias (criada no `infra/setup.sh`).
`proximo_tick` espelha o perfil (ver `proximo_tick` em `repo/base.py`): a consulta dos lembretes
usa só esse campo, então não exige índice composto e só lê os espaços que já venceram.

Antes do M14 (multiusuário) `profile`, `session` e `entries` ficavam na raiz do banco.
`FirestoreRepository(client)` ainda lê esse formato antigo: é a origem do script de migração.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from google.api_core.exceptions import AlreadyExists
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from app.domain.models import Entry, Profile, Sentence, Sessao, StatusEntrada
from app.repo.base import (
    PROCESSED_TTL,
    EntradaJaExiste,
    Repository,
    proximo_tick,
    tipo_do_espaco,
)


class FirestoreRepository:
    """O caderno de um espaço. `raiz` é qualquer coisa com `.collection(...)`: o `Client` (formato
    antigo, sem espaço) ou o documento `espacos/{id}` (e então `espaco` o aponta, para o espelho)."""

    def __init__(self, raiz: Any, espaco: firestore.DocumentReference | None = None) -> None:
        self._raiz = raiz
        self._espaco = espaco

    def obter_perfil(self) -> Profile | None:
        dados = self._raiz.collection("profile").document("me").get().to_dict()
        return Profile.model_validate(dados) if dados else None

    def salvar_perfil(self, perfil: Profile) -> None:
        self._raiz.collection("profile").document("me").set(perfil.model_dump())
        if self._espaco is not None:
            tick = proximo_tick(perfil)
            self._espaco.set(
                {
                    "tipo": tipo_do_espaco(self._espaco.id),
                    "criado_em": perfil.criado_em,
                    "proximo_tick": tick if tick is not None else firestore.DELETE_FIELD,
                },
                merge=True,
            )

    def obter_sessao(self) -> Sessao:
        dados = self._raiz.collection("session").document("current").get().to_dict()
        return Sessao.model_validate(dados) if dados else Sessao()

    def salvar_sessao(self, sessao: Sessao) -> None:
        self._raiz.collection("session").document("current").set(sessao.model_dump())

    def obter_entrada(self, slug: str) -> Entry | None:
        dados = self._raiz.collection("entries").document(slug).get().to_dict()
        return Entry.model_validate(dados) if dados else None

    def criar_entrada(self, entrada: Entry) -> None:
        try:
            self._raiz.collection("entries").document(entrada.slug).create(entrada.model_dump())
        except AlreadyExists as erro:
            raise EntradaJaExiste(entrada.slug) from erro

    def salvar_entrada(self, entrada: Entry) -> None:
        self._raiz.collection("entries").document(entrada.slug).set(entrada.model_dump())

    def listar_entradas(self, status: StatusEntrada | None = None) -> list[Entry]:
        # Filtrar por status no servidor E ordenar por data exigiria um índice composto;
        # o volume é pequeno, então a ordenação é em Python (ADR-0003).
        consulta = self._raiz.collection("entries")
        if status is not None:
            documentos = consulta.where(filter=FieldFilter("status", "==", status)).stream()
        else:
            documentos = consulta.stream()
        entradas = [Entry.model_validate(d.to_dict()) for d in documentos]
        entradas.sort(key=lambda e: (e.criado_em, e.slug))
        return entradas

    def apagar_entrada(self, slug: str) -> bool:
        documento = self._raiz.collection("entries").document(slug)
        if not documento.get().exists:
            return False
        for frase in documento.collection("sentences").stream():
            frase.reference.delete()
        documento.delete()
        return True

    def adicionar_frase(self, slug: str, frase: Sentence) -> None:
        self._raiz.collection("entries").document(slug).collection("sentences").add(
            frase.model_dump()
        )

    def listar_frases(self, slug: str) -> list[Sentence]:
        documentos = (
            self._raiz.collection("entries")
            .document(slug)
            .collection("sentences")
            .order_by("criado_em")
            .stream()
        )
        return [Sentence.model_validate(d.to_dict()) for d in documentos]

    def apagar_tudo(self) -> None:
        for entrada in self._raiz.collection("entries").stream():
            self.apagar_entrada(entrada.id)
        self._raiz.collection("profile").document("me").delete()
        self._raiz.collection("session").document("current").delete()
        if self._espaco is not None:
            self._espaco.delete()


class FirestoreBanco:
    def __init__(self, client: firestore.Client) -> None:
        self._db = client

    def do_espaco(self, espaco_id: str) -> Repository:
        documento = self._db.collection("espacos").document(espaco_id)
        return FirestoreRepository(documento, espaco=documento)

    def listar_espacos_com_lembrete(self, agora: datetime) -> list[str]:
        consulta = self._db.collection("espacos").where(
            filter=FieldFilter("proximo_tick", "<=", agora)
        )
        return [d.id for d in consulta.stream()]

    def marcar_processada(self, message_id: str, agora: datetime) -> bool:
        documento = self._db.collection("processed").document(message_id.replace("/", "_"))
        try:
            documento.create({"criado_em": agora, "expira_em": agora + PROCESSED_TTL})
        except AlreadyExists:
            return False
        return True

    def obter_numero_do_lid(self, lid: str) -> str | None:
        dados = self._db.collection("lids").document(lid).get().to_dict()
        return str(dados["numero"]) if dados else None

    def salvar_numero_do_lid(self, lid: str, numero: str) -> None:
        self._db.collection("lids").document(lid).set({"numero": numero})
