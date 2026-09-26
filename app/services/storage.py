"""Onde o arquivo exportado é guardado e como o aluno o baixa (seção 7.3 da spec).

Em produção: Cloud Storage (bucket privado) + URL assinada V4 de 24 h. Como a VM não tem chave
privada, a assinatura passa pelo IAM `signBlob`: a conta de serviço precisa do papel
`roles/iam.serviceAccountTokenCreator` sobre ela mesma.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any, Protocol

import google.auth
from google.api_core.exceptions import NotFound
from google.auth.transport.requests import Request
from google.cloud.storage import Client as ClienteStorage

VALIDADE_DO_LINK = timedelta(hours=24)
TIPO_PADRAO = "text/plain; charset=utf-8"
_ESCOPO = "https://www.googleapis.com/auth/cloud-platform"


class Armazenamento(Protocol):
    def enviar(self, nome: str, conteudo: bytes, tipo: str = TIPO_PADRAO) -> str:
        """Guarda o arquivo e devolve o link para baixá-lo."""
        ...


class CacheAudio(Protocol):
    """Guarda o áudio de pronúncia (M23) sem prazo de validade: um objeto por nome."""

    def obter(self, nome: str) -> bytes | None: ...

    def guardar(self, nome: str, conteudo: bytes) -> None: ...

    def uri(self, nome: str) -> str:
        """O link estável do objeto, para gravar no banco (não expira, ao contrário do assinado)."""
        ...


class CacheAudioEmMemoria:
    """Para testes."""

    def __init__(self) -> None:
        self.arquivos: dict[str, bytes] = {}

    def obter(self, nome: str) -> bytes | None:
        return self.arquivos.get(nome)

    def guardar(self, nome: str, conteudo: bytes) -> None:
        self.arquivos[nome] = conteudo

    def uri(self, nome: str) -> str:
        return f"memoria://{nome}"


class CacheAudioLocal:
    """Para o simulador e o desenvolvimento local: arquivos numa pasta."""

    def __init__(self, diretorio: Path) -> None:
        self._diretorio = diretorio

    def obter(self, nome: str) -> bytes | None:
        arquivo = self._diretorio / nome
        return arquivo.read_bytes() if arquivo.is_file() else None

    def guardar(self, nome: str, conteudo: bytes) -> None:
        destino = self._diretorio / nome
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(conteudo)

    def uri(self, nome: str) -> str:
        return (self._diretorio / nome).resolve().as_uri()


class CacheAudioGcs:
    """Bucket próprio, sem regra de expiração (o dos exports apaga tudo em 7 dias)."""

    def __init__(self, *, bucket: Any) -> None:
        self._bucket = bucket

    def obter(self, nome: str) -> bytes | None:
        try:
            conteudo: bytes = self._bucket.blob(nome).download_as_bytes()
        except NotFound:
            return None
        return conteudo

    def guardar(self, nome: str, conteudo: bytes) -> None:
        self._bucket.blob(nome).upload_from_string(conteudo, content_type="audio/ogg")

    def uri(self, nome: str) -> str:
        return f"gs://{self._bucket.name}/{nome}"


class ArmazenamentoEmMemoria:
    """Para testes: guarda os bytes num dicionário."""

    def __init__(self) -> None:
        self.arquivos: dict[str, bytes] = {}

    def enviar(self, nome: str, conteudo: bytes, tipo: str = TIPO_PADRAO) -> str:  # noqa: ARG002
        self.arquivos[nome] = conteudo
        return f"memoria://{nome}"


class ArmazenamentoLocal:
    """Para o simulador e o desenvolvimento local: grava numa pasta e devolve o caminho."""

    def __init__(self, diretorio: Path) -> None:
        self._diretorio = diretorio

    def enviar(self, nome: str, conteudo: bytes, tipo: str = TIPO_PADRAO) -> str:  # noqa: ARG002
        destino = self._diretorio / Path(nome).name
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(conteudo)
        return destino.resolve().as_uri()


def _renovar_token(credenciais: Any) -> None:
    credenciais.refresh(Request())


class ArmazenamentoGcs:
    def __init__(
        self,
        *,
        bucket: Any,
        credenciais: Any,
        validade: timedelta = VALIDADE_DO_LINK,
        renovar: Callable[[Any], None] = _renovar_token,
    ) -> None:
        self._bucket = bucket
        self._credenciais = credenciais
        self._validade = validade
        self._renovar = renovar

    def enviar(self, nome: str, conteudo: bytes, tipo: str = TIPO_PADRAO) -> str:
        blob = self._bucket.blob(nome)
        blob.upload_from_string(conteudo, content_type=tipo)
        # Precisa de um access token válido (e, na VM, do e-mail real da conta de serviço, que só
        # aparece depois do primeiro refresh) para assinar via IAM signBlob.
        self._renovar(self._credenciais)
        link: str = blob.generate_signed_url(
            version="v4",
            expiration=self._validade,
            method="GET",
            service_account_email=self._credenciais.service_account_email,
            access_token=self._credenciais.token,
            response_disposition=f'attachment; filename="{Path(nome).name}"',
        )
        return link


def criar_armazenamento_gcs(*, projeto: str, bucket: str) -> ArmazenamentoGcs:
    credenciais, _ = google.auth.default(scopes=[_ESCOPO])
    cliente = ClienteStorage(project=projeto, credentials=credenciais)
    return ArmazenamentoGcs(bucket=cliente.bucket(bucket), credenciais=credenciais)


def criar_cache_audio_gcs(*, projeto: str, bucket: str) -> CacheAudioGcs:
    credenciais, _ = google.auth.default(scopes=[_ESCOPO])
    cliente = ClienteStorage(project=projeto, credentials=credenciais)
    return CacheAudioGcs(bucket=cliente.bucket(bucket))
