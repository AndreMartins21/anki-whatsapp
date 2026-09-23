"""Cliente HTTP do WAHA (seção 8.3): send_text, send_file, send_seen, typing(on/off), session_status.

Corpos de request confirmados na doc atual do WAHA (waha.devlike.pro/docs/how-to/*):
`{"session": ..., "chatId": ...}` mais o campo específico de cada endpoint.
"""

from __future__ import annotations

import asyncio
import base64
import logging

import httpx
from pydantic import SecretStr

logger = logging.getLogger(__name__)


class WahaChannel:
    """Implementa `ChannelComLid`. Timeout de 15s, até 2 novas tentativas com backoff para 5xx.

    Os logs nunca incluem a API key (ela só entra no header `X-Api-Key`, nunca é logada).
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: SecretStr,
        session: str,
        timeout: float = 15.0,
        timeout_arquivo: float = 90.0,
        max_tentativas: int = 3,
        backoff_base: float = 0.5,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._session = session
        self._max_tentativas = max_tentativas
        self._timeout_arquivo = timeout_arquivo
        self._backoff_base = backoff_base
        self._cliente = httpx.AsyncClient(
            base_url=base_url,
            headers={"X-Api-Key": api_key.get_secret_value()},
            timeout=timeout,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._cliente.aclose()

    async def send_text(self, chat_id: str, text: str) -> None:
        await self._post(
            "/api/sendText", {"session": self._session, "chatId": chat_id, "text": text}
        )

    async def send_file(
        self, chat_id: str, nome: str, conteudo: bytes, tipo: str, legenda: str = ""
    ) -> None:
        """`POST /api/sendFile` com o arquivo em base64 (`file.data`). Sem retentativa e com
        timeout maior: reenviar uma resposta lenta duplicaria o arquivo no WhatsApp; se falhar,
        quem chama decide (o `/export` cai no link)."""
        await self._com_retentativas(
            "POST",
            "/api/sendFile",
            json={
                "session": self._session,
                "chatId": chat_id,
                "file": {
                    "mimetype": tipo,
                    "filename": nome,
                    "data": base64.b64encode(conteudo).decode("ascii"),
                },
                "caption": legenda,
            },
            tentativas=1,
            limite_segundos=self._timeout_arquivo,
        )

    async def send_seen(self, chat_id: str) -> None:
        await self._post("/api/sendSeen", {"session": self._session, "chatId": chat_id})

    async def typing(self, chat_id: str, on: bool) -> None:
        endpoint = "/api/startTyping" if on else "/api/stopTyping"
        await self._post(endpoint, {"session": self._session, "chatId": chat_id})

    async def session_status(self) -> str:
        resposta = await self._get(f"/api/sessions/{self._session}")
        status = resposta.json()["status"]
        return str(status)

    async def resolve_lid(self, lid: str) -> str | None:
        """`GET /api/{session}/lids/{lid}` -> {"lid": ..., "pn": "...@c.us" | null}."""
        numero_lid = lid.split("@", 1)[0]
        resposta = await self._get(f"/api/{self._session}/lids/{numero_lid}")
        pn = resposta.json().get("pn")
        return str(pn).split("@", 1)[0] if pn else None

    async def _get(self, path: str) -> httpx.Response:
        return await self._com_retentativas("GET", path, json=None)

    async def _post(self, path: str, corpo: dict[str, object]) -> httpx.Response:
        return await self._com_retentativas("POST", path, json=corpo)

    async def _com_retentativas(
        self,
        metodo: str,
        path: str,
        *,
        json: dict[str, object] | None,
        tentativas: int | None = None,
        limite_segundos: float | None = None,
    ) -> httpx.Response:
        ultimo_erro: Exception | None = None
        max_tentativas = tentativas or self._max_tentativas
        for tentativa in range(max_tentativas):
            try:
                if limite_segundos is None:
                    resposta = await self._cliente.request(metodo, path, json=json)
                else:
                    resposta = await self._cliente.request(
                        metodo, path, json=json, timeout=limite_segundos
                    )
            except httpx.TransportError as exc:
                ultimo_erro = exc
                logger.warning(
                    "falha de rede ao chamar %s %s (tentativa %d)", metodo, path, tentativa + 1
                )
            else:
                if resposta.status_code < 500:
                    resposta.raise_for_status()
                    return resposta
                ultimo_erro = httpx.HTTPStatusError(
                    f"WAHA respondeu {resposta.status_code}",
                    request=resposta.request,
                    response=resposta,
                )
                logger.warning(
                    "WAHA respondeu %d em %s %s (tentativa %d)",
                    resposta.status_code,
                    metodo,
                    path,
                    tentativa + 1,
                )
            if tentativa < max_tentativas - 1:
                await asyncio.sleep(self._backoff_base * (2**tentativa))
        if ultimo_erro is None:
            raise RuntimeError("_com_retentativas terminou sem sucesso nem erro registrado")
        raise ultimo_erro
