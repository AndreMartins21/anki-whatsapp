#!/usr/bin/env bash
# Configuração comum dos scripts de infra — é "sourced" pelos outros, não executa nada sozinho.
# Valores não secretos vêm de infra/.env.infra (não versionado; modelo em .env.infra.example).
# shellcheck shell=bash
# shellcheck disable=SC2034  # as variáveis são usadas pelos scripts que fazem `source` deste arquivo

INFRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAIZ_DIR="$(dirname "$INFRA_DIR")"

if [[ -f "$INFRA_DIR/.env.infra" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$INFRA_DIR/.env.infra"
  set +a
fi

# Sem prompts do gcloud: um "ativar a API? (y/N)" numa leitura nunca deve ativar nada por acidente
# (o setup.sh já pergunta uma vez, no começo, antes de criar qualquer coisa).
export CLOUDSDK_CORE_DISABLE_PROMPTS=1

PROJECT_ID="${GCP_PROJECT_ID:-}"
if [[ -z "$PROJECT_ID" ]]; then
  PROJECT_ID="$(gcloud config get-value project 2>/dev/null || true)"
fi
if [[ -z "$PROJECT_ID" ]]; then
  echo "Defina GCP_PROJECT_ID em infra/.env.infra (ou 'gcloud config set project ...')." >&2
  exit 1
fi

REGION="us-central1"
ZONE="us-central1-a"
VM_NAME="vocabot-vm"
SA_NAME="vocabot-vm"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
EXPORT_BUCKET="${EXPORT_BUCKET:-${PROJECT_ID}-vocabot-exports}"
AUDIO_BUCKET="${AUDIO_BUCKET:-${PROJECT_ID}-vocabot-audio}"
TTS_VOICE="${TTS_VOICE:-en-US-Neural2-F}"
LLM_PROVIDER="${LLM_PROVIDER:-vertex_gemini}"

# Segredos que o setup.sh gera (openssl rand) sem mostrar na tela.
SEGREDOS_GERADOS=(WAHA_API_KEY WAHA_DASHBOARD_PASSWORD WAHA_HOOK_HMAC_KEY)

SSH_FLAGS=(--zone "$ZONE" --project "$PROJECT_ID" --tunnel-through-iap)

# CI/CD (infra/setup_cicd.sh, seção 10.9 da spec / ADR-0013).
GITHUB_REPO="AndreMartins21/anki-whatsapp"
WIF_POOL="github-pool"
WIF_PROVIDER="github-provider"
DEPLOY_SA_NAME="vocabot-deploy"
DEPLOY_SA_EMAIL="${DEPLOY_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

# Comandos que criam ou alteram algo passam por aqui: com DRY_RUN=1 só são mostrados.
run() {
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    printf '[dry-run]'
    printf ' %q' "$@"
    printf '\n'
  else
    "$@"
  fi
}

# Verdadeiro se o comando (de leitura) termina com sucesso.
existe() {
  "$@" &>/dev/null
}
