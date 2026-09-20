---
name: gcp-best-practices
description: Boas práticas de Google Cloud — IAM de menor privilégio, segredos no Secret Manager, autenticação sem chave (ADC/conta de serviço da VM), scripts de infraestrutura idempotentes, rede privada com IAP, Firestore/Storage, URLs assinadas e controle de custo no nível gratuito. Use SEMPRE que for escrever ou revisar scripts em infra/, rodar comandos gcloud, criar ou alterar recursos no GCP (VM, bucket, Firestore, service account, secret, firewall), configurar autenticação para Vertex AI/Firestore/Storage, fazer deploy, ou quando o usuário perguntar sobre custo, permissões ou acesso à VM.
---

# Boas práticas de GCP

## Regra zero: segredos

- **Nunca** peça, leia, imprima, logue ou grave o valor de um segredo. Nem em `echo`, nem em mensagem
  de erro, nem em comentário de commit.
- Segredos vivem no **Secret Manager**. Gere-os sem passar pela tela:
  ```bash
  openssl rand -hex 24 | gcloud secrets versions add WAHA_API_KEY --data-file=-
  ```
- Para segredos que o usuário fornece, use `read -rsp` (sem eco) e `printf '%s' "$VALOR" | gcloud
  secrets versions add ... --data-file=-`. Nunca `--data="$VALOR"` (vai para o histórico do shell) e
  nunca um arquivo temporário em disco.
- No deploy, renderize o `.env` na máquina com `umask 077` (permissão 600) e apague nada em `/tmp`.
- **Zero chaves de conta de serviço em arquivo.** Use ADC: na VM, a identidade da própria instância;
  na máquina local, `gcloud auth application-default login`. Uma chave `.json` baixada é uma
  credencial de longa duração que vaza em backup, em commit e em log.

## IAM: menor privilégio

- Uma conta de serviço **por carga de trabalho**, nunca a Compute Engine default.
- Conceda papéis **no menor escopo possível**: papel no bucket (`gcloud storage buckets add-iam-policy-binding`)
  em vez de papel no projeto, sempre que o recurso suportar.
- Prefira papéis predefinidos específicos (`roles/datastore.user`, `roles/secretmanager.secretAccessor`,
  `roles/aiplatform.user`, `roles/logging.logWriter`) a papéis básicos (`owner`, `editor`).
- Para assinar URLs numa VM sem chave privada: dê `roles/iam.serviceAccountTokenCreator` à conta de
  serviço **sobre ela mesma** e assine via IAM `signBlob`, passando `service_account_email` +
  `access_token` para `generate_signed_url`.
- Ao conceder algo, diga em uma linha por que aquele papel e por que naquele escopo.

## Scripts de infraestrutura

Todo script em `infra/` é **idempotente**: rodar duas vezes não quebra e não duplica nada.

```bash
#!/usr/bin/env bash
set -Eeuo pipefail            # falha cedo, inclusive em pipe
IFS=$'\n\t'

# padrão "criar se não existir"
if ! gcloud iam service-accounts describe "$SA_EMAIL" --project "$PROJECT_ID" &>/dev/null; then
  gcloud iam service-accounts create "$SA_NAME" --project "$PROJECT_ID"
fi
```

- `set -Eeuo pipefail` no topo, sempre. Variáveis entre aspas (`"$VAR"`).
- Configuração vem de `infra/config.sh` + `infra/.env.infra` (não versionado); nada hardcoded.
- Passe `--project "$PROJECT_ID"` explicitamente em vez de depender do `gcloud config` ambiente.
- `--quiet` só em operações já confirmadas; nunca para esconder um prompt de destruição.
- Rode `shellcheck` (está no pre-commit) e `bash -n` antes de considerar pronto.

## Antes de rodar gcloud

- Comandos de **leitura** (`describe`, `list`, `get-iam-policy`, `logs read`) podem rodar direto.
- Comandos que **criam, alteram ou apagam** qualquer coisa: mostre o comando exato e espere aprovação.
- Nunca `delete` de VM, bucket, banco ou segredo sem confirmação explícita e sem dizer o que se perde.

## Rede: privado por padrão

- Sem porta pública. SSH só via **IAP** (`gcloud compute ssh --tunnel-through-iap`), com regra de
  firewall restrita a `35.235.240.0/20` e limitada por *network tag*.
- Serviços internos conversam pela rede do Docker Compose; publique porta só em `127.0.0.1` quando
  precisar de túnel local.
- Não crie Cloud NAT, balanceador ou IP estático sem necessidade comprovada — custam e ampliam a
  superfície exposta.

## Dados

- **Firestore:** modo nativo, região próxima da VM. Use `create()` (não `set()`) quando precisar de
  idempotência por ID — ele falha se o documento já existe, que é exatamente o que uma deduplicação
  quer. Configure política de **TTL** em coleções efêmeras para não pagar armazenamento eterno.
- **Storage:** bucket com *uniform bucket-level access* e prevenção de acesso público ativada.
  Entregue arquivos por **URL assinada V4** de validade curta, nunca tornando o objeto público.
  Regra de ciclo de vida para apagar objetos temporários.
- Não guarde dado pessoal que o produto não precisa.

## Custo

- Antes de criar qualquer recurso, saiba se ele está no nível gratuito e o que ele custa fora dele.
  Neste projeto: `e2-micro` + disco standard de 30 GB em `us-central1` são gratuitos; o **IP externo
  efêmero não é**; Vertex AI é pago por uso.
- Crie um **alerta de orçamento** no projeto (Billing → Budgets) antes do primeiro deploy.
- Fixe tamanhos pequenos e `mem_limit` nos containers; máquina maior é decisão do usuário, não sua.
- `gcloud billing` e o relatório de custos são leitura — consulte antes de propor qualquer upgrade.

## Observabilidade

- Logs estruturados em JSON para uma linha por evento (o Cloud Logging entende `severity`,
  `message`, e campos extras viram labels pesquisáveis).
- **Nunca** logue token, API key, número de telefone completo ou conteúdo sensível de mensagem.
- Erro de chamada externa: logue status, endpoint e tempo — não o corpo inteiro da resposta.

## Ao terminar uma mudança de infraestrutura

Diga: o que foi criado/alterado, em que projeto, quanto custa (ou "dentro do nível gratuito"), e qual
o comando de leitura que comprova o estado final.
