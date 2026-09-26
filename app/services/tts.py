"""Síntese de voz (M23, ADR-0024): o texto vira áudio OGG/Opus, o formato que o WhatsApp mostra como
nota de voz. Em produção, Google Cloud Text-to-Speech com a conta de serviço da VM (sem chave)."""

from __future__ import annotations

from typing import Any, Protocol

from google.cloud import texttospeech


class Sintetizador(Protocol):
    def sintetizar(self, texto: str, voz: str) -> bytes:
        """Áudio OGG/Opus de `texto` falado por `voz` (ex.: `en-US-Neural2-F`). Síncrono."""
        ...


def _idioma_da_voz(voz: str) -> str:
    """`en-US-Neural2-F` -> `en-US`: a API exige o idioma junto com o nome da voz."""
    return "-".join(voz.split("-")[:2])


class GoogleTts:
    def __init__(self, cliente: Any | None = None) -> None:
        self._cliente = cliente

    def _cliente_da_api(self) -> Any:
        if self._cliente is None:  # criado só no primeiro uso: a subida do bot não depende disto
            self._cliente = texttospeech.TextToSpeechClient()
        return self._cliente

    def sintetizar(self, texto: str, voz: str) -> bytes:
        resposta = self._cliente_da_api().synthesize_speech(
            input=texttospeech.SynthesisInput(text=texto),
            voice=texttospeech.VoiceSelectionParams(language_code=_idioma_da_voz(voz), name=voz),
            audio_config=texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.OGG_OPUS
            ),
        )
        conteudo: bytes = resposta.audio_content
        return conteudo
