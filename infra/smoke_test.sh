#!/usr/bin/env bash
# Confere, pela VM, que o bot responde no /health e que a sessão do WAHA está WORKING.
set -Eeuo pipefail
IFS=$'\n\t'

# shellcheck source=infra/config.sh
source "$(dirname "${BASH_SOURCE[0]}")/config.sh"

# O script remoto roda inteiro como root (o /opt/vocabot é modo 700) e lê a API key do .env da VM
# sem nunca imprimi-la.
read -r -d '' REMOTO <<'CMD' || true
set -Eeuo pipefail
cd /opt/vocabot/app
docker compose --env-file /opt/vocabot/.env ps
docker compose --env-file /opt/vocabot/.env exec -T bot python -c \
  "import urllib.request; print('bot /health:', urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5).read().decode())" </dev/null
KEY="$(grep '^WAHA_API_KEY=' /opt/vocabot/.env | cut -d= -f2-)"
STATUS="$(curl -fsS -H "X-Api-Key: $KEY" http://127.0.0.1:3000/api/sessions/default \
  | python3 -c 'import sys, json; print(json.load(sys.stdin)["status"])')"
echo "sessão do WAHA: $STATUS"
[[ "$STATUS" == "WORKING" ]]
echo SMOKE_OK
CMD

# O `docker compose exec` lê o stdin: por isso o </dev/null acima, e por isso o sucesso só vale
# se o script remoto chegou ao fim e imprimiu o marcador (um exit 0 sozinho não prova nada).
saida="$(gcloud compute ssh "$VM_NAME" "${SSH_FLAGS[@]}" --command "sudo bash -s" <<<"$REMOTO" 2>&1)" || true
printf '%s\n' "$saida" | grep -v -e NumPy -e 'please see' -e '^WARNING:' -e '^$'
if grep -q '^SMOKE_OK$' <<<"$saida"; then
  echo "Smoke test ok."
else
  echo "Smoke test FALHOU (o bot, a sessão do WAHA ou ambos não estão prontos)." >&2
  exit 1
fi
