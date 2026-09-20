#!/usr/bin/env bash
# Abre um shell na VM via IAP (não há porta de SSH pública).
set -Eeuo pipefail
IFS=$'\n\t'

# shellcheck source=infra/config.sh
source "$(dirname "${BASH_SOURCE[0]}")/config.sh"

exec gcloud compute ssh "$VM_NAME" "${SSH_FLAGS[@]}"
