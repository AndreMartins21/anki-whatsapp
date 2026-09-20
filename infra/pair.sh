#!/usr/bin/env bash
# Abre o túnel IAP para o painel do WAHA e mostra como parear o WhatsApp (seção 10.5).
set -Eeuo pipefail
IFS=$'\n\t'

# shellcheck source=infra/config.sh
source "$(dirname "${BASH_SOURCE[0]}")/config.sh"

cat <<TEXTO
Túnel aberto em http://localhost:3000 (Ctrl+C fecha).

  1. Abra http://localhost:3000/dashboard
  2. Entre com o usuário 'admin' e a senha do painel.
  3. Inicie/abra a sessão 'default' e escaneie o QR com o app WhatsApp Business do número
     do bot (Aparelhos conectados → Conectar um aparelho).

Para ver a senha do painel — só quando VOCÊ precisar, neste terminal:
  gcloud secrets versions access latest --secret=WAHA_DASHBOARD_PASSWORD --project $PROJECT_ID

TEXTO

exec gcloud compute ssh "$VM_NAME" "${SSH_FLAGS[@]}" -- -N -L 3000:localhost:3000
