#!/usr/bin/env bash
# Confere, pela VM, que o bot responde no /health e que a sessão do WAHA está WORKING.
set -Eeuo pipefail
IFS=$'\n\t'

# shellcheck source=infra/config.sh
source "$(dirname "${BASH_SOURCE[0]}")/config.sh"

# O comando remoto lê a API key do .env da VM sem nunca imprimi-la.
read -r -d '' REMOTO <<'CMD' || true
set -Eeuo pipefail
cd /opt/vocabot/app
sudo docker compose --env-file /opt/vocabot/.env ps
sudo docker compose --env-file /opt/vocabot/.env exec -T bot python -c \
  "import urllib.request; print('bot /health:', urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5).read().decode())"
KEY="$(sudo grep '^WAHA_API_KEY=' /opt/vocabot/.env | cut -d= -f2-)"
STATUS="$(curl -fsS -H "X-Api-Key: $KEY" http://127.0.0.1:3000/api/sessions/default \
  | python3 -c 'import sys, json; print(json.load(sys.stdin)["status"])')"
echo "sessão do WAHA: $STATUS"
[[ "$STATUS" == "WORKING" ]]
CMD

gcloud compute ssh "$VM_NAME" "${SSH_FLAGS[@]}" --command "$REMOTO"
echo "Smoke test ok."
