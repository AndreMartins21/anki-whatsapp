# ADR-0007: Infra no menor privilégio, segredos gerados no Secret Manager e SSH só por IAP com OS Login

- **Status:** Aceito
- **Data:** 2026-09-20
- **Fonte:** `spec/spec-inicial.md` seções 3, 10.2 a 10.7 e a skill `gcp-best-practices`

## Contexto

A VM guarda a sessão de um WhatsApp real e chama o Vertex AI com a identidade dela; um vazamento de
credencial custa dinheiro e expõe a conta. Só há um usuário e nenhuma pessoa de operações: o processo de
deploy precisa ser repetível, revisável antes de executar e nunca mostrar um segredo.

## Decisão

- Os segredos (`WAHA_API_KEY`, `WAHA_DASHBOARD_PASSWORD`, `WAHA_HOOK_HMAC_KEY`) são gerados por
  `openssl rand` no `setup.sh` e vão por pipe para o Secret Manager, sem passar pela tela. Rodar o script
  de novo não rotaciona os que já existem. A VM os lê com a própria identidade e renderiza o `.env` (modo
  600) no deploy.
- Uma conta de serviço só para a VM, com `datastore.user`, `logging.logWriter` e `aiplatform.user` no
  projeto; `secretmanager.secretAccessor` **em cada segredo** (não no projeto); `storage.objectAdmin` só no
  bucket; `serviceAccountTokenCreator` só sobre ela mesma, para assinar as URLs do export via IAM signBlob.
- Sem chave de conta de serviço em arquivo (ADC em todo lugar) e sem porta pública: SSH só via IAP e
  **OS Login** ligado na VM, em vez de chaves SSH espalhadas nos metadados do projeto.
- Todo script que altera algo aceita `DRY_RUN=1`, que imprime cada comando e só executa as leituras; os
  scripts rodam com os prompts do gcloud desligados, para uma leitura nunca ativar uma API por acidente.
- O `WAHA_HOOK_HMAC_KEY` (validação do webhook) entrou como segredo além dos dois da spec, e a senha do
  painel do WAHA também protege o Swagger, para não multiplicar segredos que só existem atrás do túnel.

## Alternativas consideradas

- **`secretAccessor` no projeto (como a lista da spec)** — mais simples, mas dá acesso a qualquer segredo
  futuro do projeto; o custo de fazer por segredo é uma linha no script.
- **Chaves SSH nos metadados do projeto** — é o que o `gcloud compute ssh` faz sem OS Login, mas mistura o acesso
  à VM com todas as outras VMs do projeto.
- **Segredos digitados pelo operador** — mais uma etapa manual e mais uma chance de o valor cair no histórico do
  shell; só a chave da Anthropic (que ninguém pode gerar) segue esse caminho, com `read -s`.

## Consequências

- Fácil: revisar o que vai acontecer antes de autorizar; refazer o setup sem duplicar nem rotacionar nada.
- Difícil: rotacionar um segredo é manual (`gcloud secrets versions add` + novo deploy). O `.env` na VM é
  um arquivo em disco (modo 600): quem tem root na VM o lê. Quem faz o deploy precisa de OS Login
  (`roles/compute.osAdminLogin`, já incluído em Owner).
- Revisitar se: houver mais de uma VM ou mais de uma pessoa operando.
