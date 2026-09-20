#!/usr/bin/env bash
# Acompanha os logs dos containers na VM. Uso: bash infra/logs.sh [waha|bot]
set -Eeuo pipefail
IFS=$'\n\t'

# shellcheck source=infra/config.sh
source "$(dirname "${BASH_SOURCE[0]}")/config.sh"

servico="${1:-}"
exec gcloud compute ssh "$VM_NAME" "${SSH_FLAGS[@]}" --command \
  "cd /opt/vocabot/app && sudo docker compose --env-file /opt/vocabot/.env logs -f --tail=200 $servico"
