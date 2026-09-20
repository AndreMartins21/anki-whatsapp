# Vocabot

Bot de WhatsApp, de uso pessoal, para praticar vocabulário de inglês (nível B1→B2) e exportar os
cartões para o **Anki**. Você manda uma palavra, o bot explica, você escreve uma frase, ele avalia —
e tudo isso vira cartão.

> **Status:** em construção. A especificação completa está em
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
spec/       especificação      .claude/skills/  skills do projeto (sdd, gcp-best-practices)
```

## Contribuindo (ou voltando aqui em três meses)

- Commits atômicos, mensagem no imperativo, um commit por marco.
- Lógica de negócio nova entra por TDD (teste primeiro).
- Decisão com consequência duradoura vira ADR em `docs/adr/`.
- Mudou um contrato? A spec é atualizada no mesmo commit.
