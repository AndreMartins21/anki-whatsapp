#!/usr/bin/env bash
# Provisiona o snapshot diário de métricas no GCP (M28, ADR-0029, seção 3.6 do
# spec/plano-dashboard.md). Idempotente, mesmo padrão de infra/setup.sh.
#
#   DRY_RUN=1 bash infra/setup_metricas.sh   # só mostra o que criaria/alteraria
#   bash infra/setup_metricas.sh             # pergunta antes de criar
#
# Custo: bucket (KB/dia) e dataset do BigQuery ficam nas cotas gratuitas (seção 1.3 do plano).
# Este script NÃO cria as tabelas externas nem as views (isso é o próximo passo, manual, depois
# de rodar `python -m scripts.snapshot --executar` pelo menos uma vez — a tabela externa precisa
# de pelo menos um arquivo na partição para o `bq mk --external_table_definition` inferir certo).
#
# [confirmar] (seção 3.6 do plano): um dataset `US` (multi-região) lê uma tabela externa apontando
# para um bucket regional (`us-central1`, como os demais buckets deste projeto) — `us-central1`
# está dentro da multi-região `US`, mas confirme na primeira consulta antes de dar como certo.
set -Eeuo pipefail
IFS=$'\n\t'

# shellcheck source=infra/config.sh
source "$(dirname "${BASH_SOURCE[0]}")/config.sh"

echo "Projeto: $PROJECT_ID | conta: $(gcloud config get-value account 2>/dev/null)"
if [[ "${DRY_RUN:-0}" != "1" ]]; then
  read -r -p "Criar/atualizar recursos de métricas neste projeto? [s/N] " resposta
  [[ "$resposta" == "s" || "$resposta" == "S" ]] || { echo "Cancelado."; exit 1; }
fi

echo "==> 1. APIs (bigquery, além das que setup.sh já ativa)"
run gcloud services enable bigquery.googleapis.com --project "$PROJECT_ID"

echo "==> 2. Bucket gs://$METRICS_BUCKET ($REGION, privado, termos/ expira em 30 dias, resto em 400)"
if ! existe gcloud storage buckets describe "gs://$METRICS_BUCKET" --project "$PROJECT_ID"; then
  run gcloud storage buckets create "gs://$METRICS_BUCKET" --location="$REGION" \
    --uniform-bucket-level-access --public-access-prevention --project "$PROJECT_ID"
fi
run gcloud storage buckets update "gs://$METRICS_BUCKET" \
  --lifecycle-file="$INFRA_DIR/lifecycle-metricas.json" --project "$PROJECT_ID"
# A SA da VM só ESCREVE neste bucket — sem leitura de outros, sem acesso ao BigQuery (ADR-0029):
# quem lê os dados é a SA do painel (M30), com objectViewer só aqui.
run gcloud storage buckets add-iam-policy-binding "gs://$METRICS_BUCKET" \
  --member="serviceAccount:$SA_EMAIL" --role=roles/storage.objectCreator \
  --project "$PROJECT_ID" --format=none

echo "==> 3. Dataset $METRICS_DATASET ($METRICS_LOCATION)"
if ! existe bq --project_id="$PROJECT_ID" show --dataset "$METRICS_DATASET"; then
  run bq --project_id="$PROJECT_ID" --location="$METRICS_LOCATION" mk --dataset \
    --description="Snapshot diário de métricas do Vocabot (M28, ADR-0029)" \
    "${PROJECT_ID}:${METRICS_DATASET}"
fi

echo
echo "Pronto. Próximos passos (manuais, ver seção 3.6 do plano):"
echo "  1. python -m scripts.snapshot --projeto $PROJECT_ID --bucket $METRICS_BUCKET --executar"
echo "  2. Para cada tabela em infra/bq/*.json, criar a tabela externa (particionamento Hive):"
echo "     bq mk --external_table_definition=@infra/bq/espacos.json@NEWLINE_DELIMITED_JSON=gs://$METRICS_BUCKET/snapshot/espacos/'{dt:DATE}'/* \\"
echo "       --hive_partitioning_mode=AUTO --hive_partitioning_source_uri_prefix=gs://$METRICS_BUCKET/snapshot/espacos \\"
echo "       ${PROJECT_ID}:${METRICS_DATASET}.espacos"
echo "     (repita para pessoas, admins, termos, grupos_pendentes, firestore_uso)"
echo "  3. Criar as views de infra/bq/views/*.sql (ainda não escritas — M30)."
echo "Conferir (só leitura): bq ls --project_id=$PROJECT_ID $METRICS_DATASET"
