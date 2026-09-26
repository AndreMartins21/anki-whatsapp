"""Áudio de pronúncia com cache (M23, ADR-0024).

O arquivo é endereçado pelo texto e pela voz (`audio/<voz>/<sha256>.ogg`), então o mesmo termo, ou
a mesma frase, é sintetizado uma única vez, para todos os espaços. O texto chega já limpo (sem `[[ ]]`).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from app.services.storage import CacheAudio
from app.services.tts import Sintetizador


@dataclass(frozen=True)
class AudioPronto:
    nome: str  # o objeto no cache
    uri: str  # o link para guardar no banco (`gs://bucket/nome` em produção)
    conteudo: bytes


class ServicoAudio:
    def __init__(self, sintetizador: Sintetizador, cache: CacheAudio, voz: str) -> None:
        self._sintetizador = sintetizador
        self._cache = cache
        self._voz = voz

    def obter(self, texto: str) -> AudioPronto:
        """Do cache, ou sintetiza e guarda. Síncrono (rede): quem chama usa `bloq`. Levanta se o
        TTS ou o Storage falharem, e nesse caso não grava nada."""
        limpo = " ".join(texto.split())  # a caixa fica: "US" e "us" se falam diferente
        if not limpo:
            raise ValueError("texto vazio para sintetizar")
        chave = hashlib.sha256(f"{self._voz}\n{limpo}".encode()).hexdigest()[:32]
        nome = f"audio/{self._voz}/{chave}.ogg"
        conteudo = self._cache.obter(nome)
        if conteudo is None:
            conteudo = self._sintetizador.sintetizar(limpo, self._voz)
            self._cache.guardar(nome, conteudo)
        return AudioPronto(nome=nome, uri=self._cache.uri(nome), conteudo=conteudo)
