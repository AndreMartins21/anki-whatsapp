"""Fonte de letras de música (M13, seção 5.8, ADR-0016): `LyricsProvider` e a implementação
sobre a API pública do LRCLIB (lrclib.net/docs) — sem chave, `GET /api/search` e
`GET /api/get/{id}`, que devolvem `id, trackName, artistName, albumName, duration, instrumental,
plainLyrics, syncedLyrics`.

As letras não são licenciadas (a base é colaborativa): o risco está aceito enquanto o bot for de
uso pessoal. Para trocar de fonte, basta outra implementação do `LyricsProvider`.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Protocol

import httpx

from app.domain.musica import Musica

logger = logging.getLogger(__name__)

USER_AGENT = "vocabot/0.1 (+https://github.com/AndreMartins21/anki-whatsapp)"


class LetrasIndisponiveis(Exception):
    """A fonte de letras não respondeu (rede, 5xx, resposta inesperada)."""


class LyricsProvider(Protocol):
    async def buscar(self, titulo: str, artista: str | None = None) -> list[Musica]:
        """Músicas que batem com o título (e o artista, se dado), na ordem da fonte."""
        ...

    async def obter(self, id_: int) -> Musica | None:
        """A música pelo id da fonte; `None` se não existe mais."""
        ...


def _musica(registro: dict[str, Any]) -> Musica:
    instrumental = bool(registro.get("instrumental"))
    letra = registro.get("plainLyrics")
    return Musica(
        id=int(registro["id"]),
        titulo=str(registro.get("trackName") or ""),
        artista=str(registro.get("artistName") or ""),
        letra=None if instrumental or not isinstance(letra, str) else letra,
    )


class LrclibProvider:
    """Timeout de 15 s e uma nova tentativa (com backoff) em 5xx ou falha de rede, como o
    cliente do WAHA. Qualquer outra falha vira `LetrasIndisponiveis`."""

    def __init__(
        self,
        *,
        base_url: str = "https://lrclib.net",
        timeout: float = 15.0,
        max_tentativas: int = 2,
        backoff_base: float = 0.5,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._max_tentativas = max_tentativas
        self._backoff_base = backoff_base
        self._cliente = httpx.AsyncClient(
            base_url=base_url,
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._cliente.aclose()

    async def buscar(self, titulo: str, artista: str | None = None) -> list[Musica]:
        """Com artista, `track_name` + `artist_name`. Sem artista, `track_name` (a busca livre
        `q` ordena pior: esconde a versão conhecida atrás de covers) e, se nada vier, `q`."""
        if artista:
            return await self._buscar({"track_name": titulo, "artist_name": artista})
        return await self._buscar({"track_name": titulo}) or await self._buscar({"q": titulo})

    async def _buscar(self, params: dict[str, str]) -> list[Musica]:
        resposta = await self._get("/api/search", params)
        corpo = resposta.json()
        if not isinstance(corpo, list):
            raise LetrasIndisponiveis("a busca não devolveu uma lista")
        try:
            return [_musica(registro) for registro in corpo]
        except (KeyError, TypeError, ValueError) as erro:
            raise LetrasIndisponiveis("registro da busca em formato inesperado") from erro

    async def obter(self, id_: int) -> Musica | None:
        resposta = await self._get(f"/api/get/{id_}", None, aceita_404=True)
        if resposta.status_code == 404:
            return None
        try:
            return _musica(resposta.json())
        except (KeyError, TypeError, ValueError) as erro:
            raise LetrasIndisponiveis("música em formato inesperado") from erro

    async def _get(
        self, path: str, params: dict[str, str] | None, *, aceita_404: bool = False
    ) -> httpx.Response:
        for tentativa in range(self._max_tentativas):
            try:
                resposta = await self._cliente.get(path, params=params)
            except httpx.TransportError:
                logger.warning(
                    "falha de rede ao buscar letra em %s (tentativa %d)", path, tentativa + 1
                )
            else:
                if resposta.status_code < 400 or (aceita_404 and resposta.status_code == 404):
                    return resposta
                if resposta.status_code < 500:
                    raise LetrasIndisponiveis(f"a fonte de letras respondeu {resposta.status_code}")
                logger.warning(
                    "a fonte de letras respondeu %d em %s (tentativa %d)",
                    resposta.status_code,
                    path,
                    tentativa + 1,
                )
            if tentativa < self._max_tentativas - 1:
                await asyncio.sleep(self._backoff_base * (2**tentativa))
        raise LetrasIndisponiveis("a fonte de letras não respondeu")


class FakeLyrics:
    """Dublê em memória (testes e simulador): busca por título contido, e por artista quando
    dado. `falhar=True` simula a fonte fora do ar. Use só letras inventadas."""

    def __init__(self, musicas: list[Musica], *, falhar: bool = False) -> None:
        self.musicas = musicas
        self.falhar = falhar
        self.buscas: list[tuple[str, str | None]] = []

    async def buscar(self, titulo: str, artista: str | None = None) -> list[Musica]:
        self.buscas.append((titulo, artista))
        if self.falhar:
            raise LetrasIndisponiveis("fora do ar (simulado)")
        alvo = titulo.lower()
        return [
            m
            for m in self.musicas
            if alvo in m.titulo.lower()
            and (artista is None or artista.lower() in m.artista.lower())
        ]

    async def obter(self, id_: int) -> Musica | None:
        if self.falhar:
            raise LetrasIndisponiveis("fora do ar (simulado)")
        return next((m for m in self.musicas if m.id == id_), None)
