#!/usr/bin/env bash
# Abre o túnel IAP para o painel do WAHA e mostra como parear o WhatsApp (seção 10.5).
set -Eeuo pipefail
IFS=$'\n\t'

# shellcheck source=infra/config.sh
source "$(dirname "${BASH_SOURCE[0]}")/config.sh"

# Porta LOCAL do túnel. Não é a 3000 por padrão: é comum já haver algo nela (outro app, outro
# container), e aí o navegador fala com esse outro serviço e o login "não funciona".
PORTA_LOCAL="${PORTA_LOCAL:-13000}"
if (ss -ltn 2>/dev/null || netstat -ltn 2>/dev/null) | grep -qE "[:.]${PORTA_LOCAL}[[:space:]]"; then
  echo "A porta local ${PORTA_LOCAL} já está em uso. Rode: PORTA_LOCAL=<outra porta> bash infra/pair.sh" >&2
  exit 1
fi

cat <<TEXTO
Túnel aberto em http://localhost:${PORTA_LOCAL} (Ctrl+C fecha).

  1. Abra http://localhost:${PORTA_LOCAL}/dashboard
  2. Entre com o usuário 'admin' e a senha do painel.
  3. Inicie/abra a sessão 'default' e escaneie o QR com o app WhatsApp Business do número
     do bot (Aparelhos conectados → Conectar um aparelho).

Para ver a senha do painel — só quando VOCÊ precisar, neste terminal:
  gcloud secrets versions access latest --secret=WAHA_DASHBOARD_PASSWORD --project $PROJECT_ID

TEXTO

exec gcloud compute ssh "$VM_NAME" "${SSH_FLAGS[@]}" -- -N -L "${PORTA_LOCAL}:localhost:3000"
