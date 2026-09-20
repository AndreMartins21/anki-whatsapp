#!/usr/bin/env bash
# Empacota o código, copia para a VM e sobe o compose (seção 10.4). Repetível.
# O .env da VM é renderizado LÁ a partir do Secret Manager; aqui só vão valores não secretos.
set -Eeuo pipefail
IFS=$'\n\t'

# shellcheck source=infra/config.sh
source "$(dirname "${BASH_SOURCE[0]}")/config.sh"

: "${ALLOWED_NUMBER:?defina ALLOWED_NUMBER em infra/.env.infra}"
: "${BOT_NUMBER:?defina BOT_NUMBER em infra/.env.infra}"
if [[ "$LLM_PROVIDER" == "vertex_gemini" ]]; then
  : "${GEMINI_MODEL:?defina GEMINI_MODEL em infra/.env.infra}"
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
chmod 700 "$TMP"

# Só o que a imagem precisa (sem .git, .env*, tests, evals, docs...).
(cd "$RAIZ_DIR" && tar czf "$TMP/vocabot.tgz" \
  Dockerfile docker-compose.yml .dockerignore pyproject.toml uv.lock app)

# Valores NÃO secretos do .env (os segredos entram na VM, direto do Secret Manager).
{
  printf 'APP_ENV=prod\n'
  printf 'LOG_LEVEL=%s\n' "${LOG_LEVEL:-INFO}"
  printf 'ALLOWED_NUMBER=%s\n' "$ALLOWED_NUMBER"
  printf 'BOT_NUMBER=%s\n' "$BOT_NUMBER"
  printf 'USER_LEVEL=%s\n' "${USER_LEVEL:-B1-B2}"
  printf 'PRACTICE_MODE=%s\n' "${PRACTICE_MODE:-guiado}"
  printf 'WAHA_URL=http://waha:3000\n'
  printf 'WAHA_SESSION=default\n'
  printf 'LLM_PROVIDER=%s\n' "$LLM_PROVIDER"
  printf 'GCP_PROJECT_ID=%s\n' "$PROJECT_ID"
  printf 'VERTEX_LOCATION=%s\n' "${VERTEX_LOCATION:-global}"
  printf 'GEMINI_MODEL=%s\n' "${GEMINI_MODEL:-}"
  printf 'GEMINI_MODEL_EVAL=%s\n' "${GEMINI_MODEL_EVAL:-}"
  printf 'ANTHROPIC_MODEL=%s\n' "${ANTHROPIC_MODEL:-claude-haiku-4-5-20251001}"
  printf 'EXPORT_BUCKET=%s\n' "$EXPORT_BUCKET"
} > "$TMP/vocabot.env.base"

echo "==> Copiando para $VM_NAME (via IAP)"
gcloud compute scp "${SSH_FLAGS[@]}" \
  "$TMP/vocabot.tgz" "$TMP/vocabot.env.base" "$INFRA_DIR/vm/render_e_subir.sh" \
  "$VM_NAME":/tmp/

echo "==> Renderizando o .env e subindo o compose na VM"
gcloud compute ssh "$VM_NAME" "${SSH_FLAGS[@]}" \
  --command "sudo bash /tmp/render_e_subir.sh '$PROJECT_ID' '$LLM_PROVIDER'; rm -f /tmp/render_e_subir.sh"
