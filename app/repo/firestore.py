"""FirestoreRepository (ADR-0003): Cloud Firestore em modo nativo, esquema da seção 7.1.

    profile/me                          session/current
    entries/{slug}                      entries/{slug}/sentences/{auto}
    processed/{message_id}              lids/{lid}

`processed.expira_em` é o campo da política de TTL de 7 dias (criada no `infra/setup.sh`).
"""

from __future__ import annotations

from datetime import datetime

from google.api_core.exceptions import AlreadyExists
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from app.domain.models import Entry, Profile, Sentence, Sessao, StatusEntrada
from app.repo.base import PROCESSED_TTL, EntradaJaExiste


class FirestoreRepository:
    def __init__(self, client: firestore.Client) -> None:
        self._db = client

    def obter_perfil(self) -> Profile | None:
        dados = self._db.collection("profile").document("me").get().to_dict()
        return Profile.model_validate(dados) if dados else None

    def salvar_perfil(self, perfil: Profile) -> None:
        self._db.collection("profile").document("me").set(perfil.model_dump())

    def obter_sessao(self) -> Sessao:
        dados = self._db.collection("session").document("current").get().to_dict()
        return Sessao.model_validate(dados) if dados else Sessao()

    def salvar_sessao(self, sessao: Sessao) -> None:
        self._db.collection("session").document("current").set(sessao.model_dump())

    def obter_entrada(self, slug: str) -> Entry | None:
        dados = self._db.collection("entries").document(slug).get().to_dict()
        return Entry.model_validate(dados) if dados else None

    def criar_entrada(self, entrada: Entry) -> None:
        try:
            self._db.collection("entries").document(entrada.slug).create(entrada.model_dump())
        except AlreadyExists as erro:
            raise EntradaJaExiste(entrada.slug) from erro

    def salvar_entrada(self, entrada: Entry) -> None:
        self._db.collection("entries").document(entrada.slug).set(entrada.model_dump())

    def listar_entradas(self, status: StatusEntrada | None = None) -> list[Entry]:
        # Filtrar por status no servidor E ordenar por data exigiria um índice composto;
        # o volume é pequeno, então a ordenação é em Python (ADR-0003).
        consulta = self._db.collection("entries")
        if status is not None:
            documentos = consulta.where(filter=FieldFilter("status", "==", status)).stream()
        else:
            documentos = consulta.stream()
        entradas = [Entry.model_validate(d.to_dict()) for d in documentos]
        entradas.sort(key=lambda e: (e.criado_em, e.slug))
        return entradas

    def apagar_entrada(self, slug: str) -> bool:
        documento = self._db.collection("entries").document(slug)
        if not documento.get().exists:
            return False
        for frase in documento.collection("sentences").stream():
            frase.reference.delete()
        documento.delete()
        return True

    def adicionar_frase(self, slug: str, frase: Sentence) -> None:
        self._db.collection("entries").document(slug).collection("sentences").add(
            frase.model_dump()
        )

    def listar_frases(self, slug: str) -> list[Sentence]:
        documentos = (
            self._db.collection("entries")
            .document(slug)
            .collection("sentences")
            .order_by("criado_em")
            .stream()
        )
        return [Sentence.model_validate(d.to_dict()) for d in documentos]

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
