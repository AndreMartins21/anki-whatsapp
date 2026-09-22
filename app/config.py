"""Configuração da aplicação (seção 4 da spec).

Valores não secretos vêm do `.env` local ou do ambiente (compose, VM); segredos
(`WAHA_API_KEY`, `ANTHROPIC_API_KEY`) chegam como env var também, mas nunca são lidos,
pedidos ou impressos por este projeto — em produção, o `.env` é renderizado na VM a partir
do Secret Manager (infra/deploy.sh).
"""

from __future__ import annotations

from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

NivelUsuario = Literal["A2-B1", "B1-B2", "B2-C1"]
ProvedorLLM = Literal["vertex_gemini", "anthropic"]
AmbienteApp = Literal["local", "prod"]


class Settings(BaseSettings):
    """Config tipada da aplicação, carregada de variáveis de ambiente / `.env`."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Aplicação
    app_env: AmbienteApp = "local"
    log_level: str = "INFO"

    # Usuário / canal
    allowed_number: str
    bot_number: str
    user_level: NivelUsuario = "B1-B2"

    # WAHA (gateway WhatsApp)
    waha_url: str = "http://waha:3000"
    waha_session: str = "default"
    waha_api_key: SecretStr
    # Assinatura HMAC dos webhooks (seção 8.1: "se o WAHA suportar, configure e valide" — a
    # doc atual confirma suporte via WHATSAPP_HOOK_HMAC_KEY). Opcional: sem ela, confiamos na
    # rede interna isolada do compose, como a spec permite como alternativa.
    waha_hook_hmac_key: SecretStr | None = None

    # IA
    llm_provider: ProvedorLLM = "vertex_gemini"
    gcp_project_id: str
    vertex_location: str = "global"
    gemini_model: str | None = None
    gemini_model_eval: str | None = None
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-haiku-4-5-20251001"

    # Storage
    export_bucket: str

    @field_validator(
        "waha_hook_hmac_key",
        "anthropic_api_key",
        "gemini_model",
        "gemini_model_eval",
        mode="before",
    )
    @classmethod
    def _vazio_e_nao_configurado(cls, valor: object) -> object:
        """`CHAVE=` no .env chega como texto vazio; para opcionais isso significa "não definido"."""
        if isinstance(valor, str) and not valor.strip():
            return None
        return valor
