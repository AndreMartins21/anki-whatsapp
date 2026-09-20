# Vocabot

Bot de WhatsApp, de uso pessoal, para praticar vocabulário de inglês (nível B1→B2) e exportar os
cartões para o **Anki**. Você manda uma palavra, o bot explica, você escreve uma frase, ele avalia —
e tudo isso vira cartão.

> **Status:** código pronto até o M7 (a aplicação, o compose e os scripts de `infra/`); o M8 é
> provisionar e fazer o deploy, comando a comando. A especificação completa está em
> [`spec/spec-inicial.md`](spec/spec-inicial.md); o trabalho anda marco a marco (seção 9 da spec).

## Stack

| Item | Escolha |
|---|---|
| Linguagem | Python 3.12 |
| Web | FastAPI + Uvicorn |
| Canal WhatsApp | WAHA Core (self-hosted, engine GOWS) |
| IA | Gemini no Vertex AI (SDK `google-genai`), sem chave de API |
| Banco | Firestore (modo nativo) |
| Arquivos | Cloud Storage + URL assinada V4 |
| Hospedagem | 1 VM `e2-micro` (nível gratuito) com Docker Compose |
| Ferramentas | uv, ruff, mypy, pytest, pre-commit |

O porquê de cada escolha está em [`docs/adr/0001-stack-do-mvp.md`](docs/adr/0001-stack-do-mvp.md).

## Começando

Requer [uv](https://docs.astral.sh/uv/) (ele instala o Python 3.12 sozinho):

```bash
make setup     # venv + dependências + hooks de pre-commit + .env a partir do .env.example
make check     # ruff + mypy + pytest
```

Edite o `.env` com **valores falsos** para desenvolvimento local — ele nunca é versionado, e os
testes não dependem de credencial nem de rede.

```bash
make sim       # ciclo completo no terminal, sem WhatsApp
make run       # sobe a API em http://localhost:8000 (webhook do WAHA)
make help      # todos os alvos
```

## Comandos do bot

Manda uma palavra em inglês (`stall` ou `stall | the talks stalled`) e segue o menu numerado.
`/ajuda` lista tudo: `/lista`, `/pendentes`, `/praticar [palavra]`, `/exportar [tudo]`,
`/apagar palavra`, `/nivel B1-B2`, `/cancelar`, `/status`. O `/exportar` devolve um link (válido por
24 h) para um `.txt` que o Anki importa direto no tipo de nota "Inglês – Vocabulário".

## Deploy (runbook)

Pré-requisitos: `gcloud` autenticado, projeto com faturamento, papel de Owner, e o número do bot
(chip com WhatsApp Business) à mão. **Nada abaixo roda sozinho:** cada script que cria algo pergunta
antes, e `DRY_RUN=1` só mostra os comandos.

```bash
cp infra/.env.infra.example infra/.env.infra   # preencha GCP_PROJECT_ID, ALLOWED_NUMBER, BOT_NUMBER
DRY_RUN=1 bash infra/setup.sh   # revisar o que será criado (só as leituras rodam)
bash infra/setup.sh             # APIs, Firestore + TTL, conta de serviço, bucket, segredos, firewall, VM
bash infra/deploy.sh            # empacota, copia via IAP, renderiza o .env na VM e sobe o compose
bash infra/pair.sh              # túnel (porta local 13000) p/ o painel do WAHA: escaneie o QR com o número do bot
bash infra/smoke_test.sh        # bot em /health e sessão do WAHA em WORKING
```

Depois: mande `/ajuda` do seu WhatsApp pessoal para o número do bot.

| Preciso de… | Comando |
|---|---|
| ver logs | `bash infra/logs.sh [waha\|bot]` |
| entrar na VM | `bash infra/ssh.sh` |
| atualizar o código | `bash infra/deploy.sh` (o WAHA e a sessão não são recriados) |
| ver a senha do painel | `gcloud secrets versions access latest --secret=WAHA_DASHBOARD_PASSWORD` (só quando você quiser) |
| chave da Anthropic (opcional) | `LLM_PROVIDER=anthropic bash infra/setup.sh` e depois `bash infra/secrets.sh` |

Notas de operação:

- **Custo:** `e2-micro` + disco standard de 30 GB em `us-central1` são gratuitos; o IP externo
  efêmero custa até ~US$ 3,60/mês (confira na fatura, SKU "External IP Charge on a Standard VM") e o
  Gemini é pago por uso (centavos neste volume). Crie um alerta de orçamento em Billing → Budgets
  antes do primeiro deploy. O IP existe só para a VM **sair** para a internet — nada entra nela.
  Alternativas gratuitas (casa, Oracle) e o porquê de ficarmos na GCP estão no
  [ADR-0008](docs/adr/0008-continuar-na-gcp-e-manter-a-saida-portavel.md); **revisitar antes de os
  créditos do trial acabarem**.
- **Memória (1 GB):** swap de 2 GB criado no boot, `mem_limit` de 400 MB no WAHA (engine GOWS, sem
  Chromium) e 300 MB no bot (medido: ~80 MB em repouso).
- **QR expira:** o QR vale por poucos minutos. Se a sessão aparecer como `FAILED`/`STOPPED` no painel
  (ninguém escaneou a tempo), clique em *Restart* na sessão `default` para gerar um QR novo.
- **Sessão do WhatsApp:** fica no volume `waha_sessions`; recriar o container não pede QR de novo.
  Só pode haver uma sessão ativa por número: não pareie o mesmo número em outro WAHA ao mesmo tempo.
- **Logs:** JSON, uma linha por evento, sem segredo e sem número de telefone completo. Se o bot não
  responder depois do pareamento, procure nos logs do bot por `LID não resolvido` (o WhatsApp às vezes
  identifica o remetente por um LID que o WAHA não consegue traduzir para o telefone) ou por
  `número não autorizado` (confira `ALLOWED_NUMBER`).
- **Imagem do WAHA:** tag fixada em `docker-compose.yml` (`gows-...`); para atualizar, troque a tag
  depois de ler as notas de versão em hub.docker.com/r/devlikeapro/waha.
- **Testar localmente:** `make sim` (sem WhatsApp, IA fabricada) ou `make sim ARGS=--real-llm`
  (Gemini de verdade, com `gcloud auth application-default login`); `make evals` mede a avaliação
  de frases; `make test-emulador` roda o contrato do `Repository` contra o emulador do Firestore.

## Segurança

- Segredos vivem no **Secret Manager**; na VM o `.env` é renderizado no deploy com permissão 600.
- Nenhuma chave de conta de serviço em arquivo: autenticação por ADC / identidade da VM.
- `gitleaks` roda no pre-commit e na CI; `.env`, `.env.infra` e chaves estão no `.gitignore` e há
  teste de higiene que falha se algum deles for versionado.
- Acesso à VM só por **IAP**; nenhuma porta pública.

Se um segredo vazar para um commit, ele é considerado comprometido: **rotacione primeiro**, depois
limpe o histórico.

## Estrutura

```
app/        aplicação          sim/    simulador de terminal
tests/      pytest + fixtures  evals/  qualidade dos modelos (fora do pytest)
infra/      scripts de GCP     docs/   ADRs
Dockerfile, docker-compose.yml  bot + WAHA na VM
spec/       especificação      .claude/skills/  skills do projeto (sdd, gcp-best-practices)
```

## Contribuindo (ou voltando aqui em três meses)

- Commits atômicos, mensagem no imperativo, um commit por marco.
- Lógica de negócio nova entra por TDD (teste primeiro).
- Decisão com consequência duradoura vira ADR em `docs/adr/` — ver o
  [índice](docs/adr/README.md).
- Mudou um contrato? A spec é atualizada no mesmo commit.
