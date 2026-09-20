# CLAUDE.md — Vocabot (MVP, versão WAHA + Gemini no Vertex AI)

Este arquivo é a especificação do projeto. Leia-o inteiro antes de escrever código. Trabalhe **marco a marco** (seção 9), pare ao fim de cada um para eu revisar e só avance quando eu aprovar.

---

## 1. O que estamos construindo

Um bot de WhatsApp, de uso pessoal e com um único usuário, para praticar vocabulário de inglês. O nível do usuário é **B1 indo para B2**, e ele é brasileiro (responda sempre em PT-BR).

**Canal:** o bot tem um número próprio (chip Vivo) com o app **WhatsApp Business** instalado num celular. O servidor se conecta a esse número como **aparelho conectado** (linked device) usando o **WAHA Core** (WhatsApp HTTP API, self-hosted e gratuito). O usuário conversa com o bot a partir do WhatsApp pessoal dele. **Não** usamos a Cloud API oficial da Meta.

Ciclo principal:

1. O usuário manda uma palavra ou expressão em inglês, opcionalmente com a frase onde a viu (ex.: `stall | the talks stalled`).
2. O bot explica a palavra: tradução, definição curta e uma dica. Se ela tiver mais de um sentido comum e não houver contexto, o bot pergunta qual sentido o usuário quer.
3. O bot oferece um **menu numerado**: 1 escrever uma frase, 2 ver exemplos, 3 só salvar.
4. Se o usuário escrever uma frase, o bot avalia se ela usa a palavra corretamente, naquele sentido, e se é natural. Devolve um veredito, a correção e uma versão natural. O usuário pode tentar de novo.
5. Se o usuário pedir exemplos, o bot gera 3 frases de nível B1-B2 em contextos diferentes e convida o usuário a escrever a dele.
6. Ao concluir, tudo fica salvo no Firestore: a palavra, o sentido, as frases do usuário com as avaliações e os exemplos.
7. Depois de salvar, o bot sugere de 3 a 5 **expressões relacionadas**. O usuário escolhe pelos números (ex.: `1,3`), e elas viram novas entradas para praticar agora ou depois.
8. `/exportar` gera um `.txt` para o Anki e envia um **link temporário** para baixar (seção 7.5). O WAHA Core não envia arquivos.

Fora de escopo no MVP: revisão espaçada no WhatsApp, áudio, lembretes agendados, multiusuário, painel web e conversa livre com IA.

## 2. Stack e decisões fixas

| Item | Decisão |
|---|---|
| Linguagem | Python 3.12 |
| Web | FastAPI + Uvicorn (recebe webhooks do WAHA pela rede interna do Docker) |
| Validação/config | Pydantic v2 + pydantic-settings |
| HTTP | httpx |
| IA | **Gemini no Vertex AI** (padrão): SDK `google-genai` com `vertexai=True`, `location=global`, autenticação pela conta de serviço da VM (sem chave de API). Alternativa opcional: API da Anthropic, via `LLM_PROVIDER=anthropic` |
| Gateway WhatsApp | **WAHA Core** (`devlikeapro/waha`), engine **GOWS** (sem navegador, leve), 1 sessão chamada `default` |
| Banco | Firestore (modo nativo), banco `(default)` |
| Arquivos exportados | Cloud Storage (bucket privado) + URL assinada V4 de 24 h |
| Hospedagem | **1 VM Compute Engine `e2-micro`** (nível gratuito), `us-central1`, Debian 12, disco *standard* de 30 GB, **Docker Compose** com 2 serviços: `waha` e `bot` |
| Segredos | Secret Manager → arquivo `.env` renderizado na VM no deploy (permissão 600) |
| Acesso à VM | SSH via **IAP** (`gcloud compute ssh --tunnel-through-iap`). Nenhuma porta pública além disso |
| Testes | pytest com fakes em memória para Firestore, WAHA e IA |
| Lint/format | ruff |

A VM tem só 1 GB de RAM. Crie um **swap de 2 GB**, limite a memória dos containers no compose e não use a engine WEBJS (Chromium). Não introduza outros serviços sem me perguntar.

## 3. Regras de trabalho para você (Claude Code)

1. **Nunca peça, leia, imprima ou grave valores de segredos.** Com o Vertex AI, não há chave de IA. Se um dia eu usar a Anthropic, a chave entra pelo `infra/secrets.sh`, que eu rodo em outro terminal. Os segredos internos (API key e senha do painel do WAHA) são gerados pelo `setup.sh` com `openssl rand` e vão direto para o Secret Manager, **sem** aparecer na tela.
2. Antes de rodar qualquer comando `gcloud` ou `ssh` que **crie, altere ou apague** algo, mostre o comando e espere eu aprovar. Comandos de leitura podem rodar direto.
3. Scripts de `infra/` precisam ser **idempotentes**.
4. Confira na documentação atual do WAHA (waha.devlike.pro) os nomes exatos de: variáveis de ambiente (API key, painel, webhook, engine, reinício automático de sessões), endpoints (`sendText`, `sendSeen`, `startTyping`/`stopTyping`, status da sessão, QR) e o formato do payload do evento `message`. Fixe a **versão da imagem** (tag) no compose, sem usar `latest`. Confira também, na documentação do Vertex AI e do SDK `google-genai`: o **ID do modelo Gemini Flash (ou Flash-Lite) atual e GA**, se ele exige `location=global`, qual método da SDK usar (`generate_content` ou a Interactions API, conforme o modelo) e como pedir saída estruturada (JSON com schema). **Não use a família Gemini 2.5**, que está com aposentadoria marcada para outubro/2026. Deixe o que puder configurável.
5. Todo texto voltado ao usuário fica em `app/messages.py` (PT-BR, tom amigável e curto).
6. Faça um commit ao fim de cada marco.
7. Se algo nesta especificação estiver ambíguo ou parecer errado, pergunte antes de inventar.

## 4. Configuração

| Nome | Origem | Descrição |
|---|---|---|
| `LLM_PROVIDER` | `.env.infra` | `vertex_gemini` (padrão) ou `anthropic` |
| `GEMINI_MODEL` / `GEMINI_MODEL_EVAL` | `.env.infra` | ID do modelo Gemini (confirmar o atual); o de avaliação pode ser igual ou maior |
| `VERTEX_LOCATION` | `.env.infra` | Padrão `global` |
| `GCP_PROJECT_ID` | `.env.infra` | Projeto do Google Cloud (usado pelo Vertex AI e pelos scripts) |
| `ANTHROPIC_API_KEY` | Secret Manager (opcional) | Só se `LLM_PROVIDER=anthropic` |
| `WAHA_API_KEY` | Secret Manager (gerado) | Chave que o bot usa para chamar o WAHA; o WAHA exige essa chave |
| `WAHA_DASHBOARD_PASSWORD` | Secret Manager (gerado) | Senha do painel/Swagger do WAHA (usuário `admin`) |
| `ALLOWED_NUMBER` | `.env.infra` | Número **pessoal** do usuário, só dígitos (ex.: `5531999998888`) |
| `BOT_NUMBER` | `.env.infra` | Número Vivo do bot, só dígitos (informativo/logs) |
| `WAHA_URL` | compose | `http://waha:3000` |
| `WAHA_SESSION` | compose | `default` |
| `EXPORT_BUCKET` | `.env.infra` | Nome do bucket de exportações |
| `ANTHROPIC_MODEL` | `.env.infra` (opcional) | Padrão `claude-haiku-4-5-20251001` |
| `USER_LEVEL` | `.env.infra` | Padrão `B1-B2` |
| `PRACTICE_MODE` | `.env.infra` | `guiado` (padrão) ou `producao_primeiro` |
| `APP_ENV` | compose | `local` ou `prod` |

Para desenvolvimento local, use um `.env` (no `.gitignore`) com valores falsos. Os testes nunca dependem de credenciais reais. Para o simulador com IA real (`--real-llm`), use as credenciais locais do Google (`gcloud auth application-default login`), sem chave em arquivo.

## 5. Especificação funcional

### 5.1 Máquina de estados

A sessão fica num único documento `session/current`. Todas as escolhas são por **número**; aceite também variações (`1`, `1.`, `um`, `escrever`).

```
IDLE
  └─ texto (não comando) ─────────▶ explicar ──┬─▶ AWAIT_SENSE   (vários sentidos e sem contexto)
                                                └─▶ AWAIT_CHOICE  (sentido definido)
AWAIT_SENSE   ── número válido ──▶ AWAIT_CHOICE
AWAIT_CHOICE  ── 1 ──▶ AWAIT_SENTENCE
              ── 2 ──▶ gerar exemplos ─▶ AWAIT_AFTER_EXAMPLES
              ── 3 ──▶ salvar ─▶ OFFER_EXPANSION
              ── frase com a palavra-alvo ─▶ avaliar direto (atalho) ─▶ AWAIT_NEXT
AWAIT_SENTENCE ── texto ──▶ avaliar ─▶ AWAIT_NEXT
AWAIT_NEXT    ── 1 outra frase ──▶ AWAIT_SENTENCE
              ── 2 exemplos ─────▶ gerar exemplos ─▶ AWAIT_AFTER_EXAMPLES
              ── 3 concluir ─────▶ salvar ─▶ OFFER_EXPANSION
              ── frase com a palavra-alvo ─▶ avaliar direto
AWAIT_AFTER_EXAMPLES ── 1 escrever ──▶ AWAIT_SENTENCE
                     ── 2 concluir ──▶ salvar ─▶ OFFER_EXPANSION
                     ── frase com a palavra-alvo ─▶ avaliar direto
OFFER_EXPANSION ── "1,3" (lista de números) ─▶ criar entradas "nova" ─▶ perguntar "1 praticar agora · 2 depois"
                ── 0 ou "pular" ─────────────▶ IDLE
```

Duas perguntas de 1/2 citadas nas regras abaixo também são estados (M2): `AWAIT_NEW_WORD` ("1 praticar X
agora · 2 era minha frase") e `AWAIT_EXPANSION_PRACTICE` ("1 praticar agora · 2 depois"). No modo
`producao_primeiro`, depois de explicar (ou escolher o sentido) o estado é `AWAIT_SENTENCE`, com o menu
"1 me dá um exemplo · 2 só salvar". Número solto e inválido (`7`) nunca é tratado como palavra nova.

Regras:

- **Texto que não é número válido** num estado que espera número:
  - se contiver a palavra-alvo (ou flexão), é uma frase: avalie;
  - se tiver até 4 palavras e não contiver a palavra-alvo, provavelmente é palavra nova: pergunte "1 praticar *X* agora (salvo a anterior) · 2 era minha frase";
  - nos outros casos, reenvie o menu com um lembrete curto.
- Em AWAIT_SENTENCE, texto sem a palavra-alvo e com até 4 palavras também dispara a pergunta acima.
- **Sessão parada há mais de 3 horas** volta para IDLE, salvando o que houver.
- `/cancelar` volta a IDLE sem apagar o que já foi salvo.
- **Sempre** reenvie o menu atual ao final de cada resposta do bot que espera escolha.

### 5.2 Comandos

`/ajuda`, `/lista`, `/pendentes`, `/praticar [palavra]`, `/exportar`, `/exportar tudo`, `/apagar palavra`, `/nivel B1-B2`, `/cancelar`, `/status`.

- `/pendentes` lista as entradas com status `nova`.
- `/praticar` sem argumento pega a pendente mais antiga.
- `/nivel` aceita A2-B1, B1-B2 e B2-C1.
- `/status` mostra o status da sessão do WAHA, o total de palavras e as pendentes.

### 5.3 Calibração pelo nível (B1-B2)

- **Exemplos:** vocabulário de apoio no máximo B2 (a palavra-alvo pode ser de qualquer nível), 8 a 18 palavras por frase, contextos variados (empresa internacional, dia a dia, informal).
- **Avaliação:** tolerante com frases simples e corretas. Prioridade: sentido, depois gramática e colocação, depois naturalidade. Explicação em PT-BR com no máximo 4 linhas.
- **Expansões:** colocações e expressões frequentes de nível B1-B2, ligadas ao sentido escolhido. Evite idiomatismos raros (C2).
- Cada entrada guarda `cefr_estimado`.

### 5.4 Modos de prática

- `guiado` (padrão): menu 1 escrever · 2 exemplos · 3 só salvar.
- `producao_primeiro`: pede a frase direto; o menu vira 1 me dá um exemplo · 2 só salvar.

### 5.5 Formato das mensagens

Use a formatação do WhatsApp (`*negrito*`, `_itálico_`) e emojis com moderação. Um único texto por resposta sempre que possível: explicação ou avaliação **mais** o menu, na mesma mensagem.

```
*STALL* (verbo) · B2
🇧🇷 travar, emperrar; enrolar
📖 to stop making progress
💡 "the car stalled" = o carro morreu

O que você quer fazer?
1️⃣ Escrever uma frase
2️⃣ Ver exemplos
3️⃣ Só salvar
_(ou já mande sua frase com "stall")_
```

```
⚠️ *Quase lá!* O uso de *stalled* está perfeito.
✏️ didn't sent → didn't send
✨ The project stalled because the client didn't send the documents.
💬 Depois de "didn't", o verbo fica na forma base.

1️⃣ Outra frase  ·  2️⃣ Exemplos  ·  3️⃣ Concluir
```

### 5.6 Comportamento "humano" (reduz o risco de bloqueio)

- Marque as mensagens recebidas como lidas (`sendSeen`).
- Mostre "digitando…" (`startTyping`) enquanto chama a IA e pare antes de enviar.
- Espere de 1 a 2 s (aleatório) antes de cada envio.
- **Nunca** envie mensagem para número diferente do `ALLOWED_NUMBER`.
- Nunca mande mais de 3 mensagens seguidas sem uma resposta do usuário.

## 6. Contratos com a IA

Implemente em `app/services/llm.py` uma interface `LLMProvider` com duas implementações:

- `VertexGeminiProvider` (padrão): `google-genai` com `vertexai=True`, `project=GCP_PROJECT_ID` e `location=VERTEX_LOCATION`. Peça **saída estruturada** com o schema derivado do modelo Pydantic (JSON mode com schema), conforme a documentação atual da SDK para o modelo escolhido.
- `AnthropicProvider` (opcional): *tool use* com uma única ferramenta por tarefa (`input_schema` = schema Pydantic) e `tool_choice` forçando essa ferramenta.

As funções de negócio (`explain`, `evaluate`, `examples`, `expansions`) não sabem qual provedor está em uso. Valide sempre com Pydantic, com 1 nova tentativa em caso de erro. Temperatura 0.2 a 0.3. Prompts em `app/services/prompts.py`, com o nível e o contexto do usuário ("brasileiro, trabalha numa empresa internacional, usa inglês técnico no dia a dia").

```python
class Sense(BaseModel):
    id: str; traducao: str; definicao: str; exemplo_curto: str

class Explanation(BaseModel):
    ok: bool
    motivo_erro: str | None
    palavra: str                    # forma base, minúsculas
    classe: str                     # PT-BR
    cefr_estimado: Literal["A2","B1","B2","C1","C2"]
    sentidos: list[Sense]           # 1 a 4, só os comuns
    sentido_do_contexto: str | None # id do sentido quando o contexto (ou haver um único sentido comum) o define
    frase_contexto: str | None      # frase do usuário corrigida, alvo entre [[ ]]
    nota: str
    tags: list[Literal["trabalho","phrasal_verb","expressao"]]

class Evaluation(BaseModel):
    usa_palavra_alvo: bool          # considera flexões
    sentido_correto: bool
    veredito: Literal["correta","correta_pouco_natural","quase","incorreta"]
    correcoes: list[str]            # "errado → certo"
    versao_natural: str             # alvo entre [[ ]]
    explicacao: str                 # PT-BR, máx. 4 linhas

# examples(palavra, sentido, nivel, n=3) -> list[str]   (alvo entre [[ ]], contextos distintos)

class Expansion(BaseModel):
    expressao: str; traducao: str
    tipo: Literal["colocacao","familia","phrasal_verb","sinonimo","expressao"]
# expansions(palavra, sentido, nivel, ja_existentes) -> list[Expansion]  (3 a 5, sem repetir o que já existe)
```

**Qualidade:** crie `evals/sentencas.yaml` com uns 15 casos (frase + veredito esperado) e `python -m evals.run [--provider vertex_gemini|anthropic] [--model ID]`, que mede a taxa de acerto contra a API real. Assim comparo modelos antes de escolher. Fica fora do pytest.

## 7. Dados

### 7.1 Firestore
```
profile/me                 { nivel, modo, criado_em }
session/current            { estado, entry_id, sentido_id, pendente_nova_palavra?, explicacao_pendente, expansoes_sugeridas,
                             expansoes_criadas, atualizado_em }
                           # os 3 campos guardam os menus numerados em andamento ("1,3" precisa apontar para algo)
entries/{slug}             { palavra, classe, cefr_estimado, sentido:{traducao,definicao}, outros_sentidos,
                             nota, tags, origem_texto, origem:"usuario"|"expansao", pai?, status:"nova"|"praticada",
                             exportado, criado_em, atualizado_em }
entries/{slug}/sentences/{auto}  { texto, autor:"usuario"|"bot", veredito?, correcoes?, versao_natural?, explicacao?, criado_em }
processed/{message_id}     { criado_em, expira_em }     # deduplicação; política de TTL de 7 dias
lids/{lid}                 { numero }                   # cache LID -> número (seção 8.2), evita consultar o WAHA a cada mensagem
```
- `slug`: minúsculas, `[^a-z0-9]+` → `-`. Se o mesmo slug surgir com outro sentido, use o sufixo `--s2`.
- Defina a interface `Repository` (Protocol) com `FirestoreRepository` e `MemoryRepository`. A deduplicação usa `create()`, que falha se o ID já existe.

### 7.2 Status e frase do cartão
- Uma entrada fica `praticada` quando tem ao menos uma frase do usuário avaliada; senão, é `nova`.
- A frase do cartão é a melhor frase **do usuário** (`correta`, senão a `versao_natural` mais recente). Se não houver, use o primeiro exemplo do bot.

### 7.3 Export para o Anki (formato fixo, não mude)
O tipo de nota "Inglês – Vocabulário" já existe no Anki do usuário, com os campos `Palavra, Frase, FraseLacuna, Traducao, Definicao, Nota, Producao`. Gere UTF-8 com este cabeçalho exato (o travessão é "–", U+2013):
```
#separator:tab
#html:true
#notetype:Inglês – Vocabulário
#deck:Inglês::Vocabulário
#columns:Palavra	Frase	FraseLacuna	Traducao	Definicao	Nota	Producao	Tags
#tags column:8
```
- `Frase` = frase com `<b>alvo</b>`.
- `FraseLacuna` = frase com `<span class="lacuna">_____</span>`.
- `Traducao` = `(classe) tradução`.
- `Producao` = `y`.
- `Tags` = `whatsapp` mais as tags da entrada.
- Troque tab e quebra de linha dentro dos campos por espaço e `<br>`.

**Entrega:** faça upload do arquivo em `gs://$EXPORT_BUCKET/exports/anki_AAAA-MM-DD_HHMM.txt` e gere uma **URL assinada V4 válida por 24 h**. Na VM não há chave privada, então assine via IAM `signBlob`: a conta de serviço da VM precisa do papel `roles/iam.serviceAccountTokenCreator` **sobre ela mesma**, e use `service_account_email` + `access_token` no `generate_signed_url`. Envie o link por texto com instruções curtas. O bucket tem uma regra de ciclo de vida que apaga objetos após 7 dias.

## 8. Canal: WAHA

### 8.1 Recebimento (`app/main.py`)
- O WAHA envia webhooks para `http://bot:8000/waha/webhook`, pela rede interna do compose; a porta do bot **não** é publicada. Assine só os eventos `message` e `session.status`.
- Se o WAHA suportar HMAC de webhook, configure e valide. Se não, confie na rede interna, que fica isolada.
- Para cada evento `message`:
  1. **Ignore `fromMe == true`**, para o bot não responder a si mesmo e não entrar em loop.
  2. Ignore grupos (`@g.us`), status/broadcast e canais.
  3. Aplique a allowlist (8.2).
  4. Deduplique pelo `id` da mensagem.
  5. Faça `sendSeen` e despache ao roteador, com a lógica síncrona em threadpool. A conversa (IA, atrasos "humanos") roda em segundo plano, depois do 200 (M4, ADR-0006).
  6. **Sempre** devolva 200. Registre as exceções e mande ao usuário uma mensagem curta de erro.
- Mídia (`hasMedia`, áudio, figurinha etc.): responda que o MVP só entende texto.
- `session.status`: registre no log. Se o status sair de `WORKING`, registre em nível WARNING.
- `GET /health`: `{"ok": true}`, usado pelo healthcheck do compose.

### 8.2 Allowlist e identificadores
- Em conversas 1:1, o `from` costuma vir como `NUMERO@c.us`, mas o WhatsApp também usa **LIDs** (`...@lid`). Aceite a mensagem se o número extraído bater com `ALLOWED_NUMBER` (comparando as variantes com e sem o 9 depois do DDD). Se vier um LID, resolva o número usando o endpoint de LIDs do WAHA (confira na documentação) e guarde o mapeamento em cache no Firestore.
- **Envie sempre para o chatId do `ALLOWED_NUMBER`** (`NUMERO@c.us`), nunca para outro chat.

### 8.3 Cliente (`app/channel/waha.py`)
Implemente `send_text`, `send_seen`, `typing(on/off)` e `session_status`, com o header `X-Api-Key` (ou o nome atual segundo a documentação). Timeouts de 15 s, até 2 novas tentativas com backoff para 5xx, logs **sem** a API key.

### 8.4 Adaptador de canal
Crie a interface `Channel` (enviar texto, marcar como lido, digitando) com as implementações `WahaChannel`, `ConsoleChannel` (simulador) e `FakeChannel` (testes). A lógica de negócio **não** pode importar nada do WAHA diretamente, para que seja possível trocar por Cloud API ou Telegram no futuro.

## 9. Marcos (pare ao fim de cada um)

| # | Entrega | Critério de aceite |
|---|---|---|
| M0 | Estrutura do repo, dependências, ruff, pytest, `.gitignore`, `.dockerignore`, `Dockerfile` do bot, `.env.example` | `pytest` e `ruff check` passam |
| M1 | `main.py` (webhook do WAHA, health), parser de eventos, allowlist com LID, deduplicação, cliente WAHA, interface `Channel` | Testes com payloads de exemplo em `tests/fixtures/`: texto, `fromMe`, grupo, mídia, número não autorizado, LID, duplicado, `session.status` |
| M2 | Modelos, `Repository` (memória e Firestore), máquina de estados, parser de escolhas numéricas | Testes de todas as transições da seção 5.1, incluindo os atalhos |
| M3 | `llm.py`, `prompts.py`, schemas, `FakeLLM`, `evals/` | Testes com o fake; `python -m evals.run` funciona se houver chave |
| M4 | Fluxos e comandos completos | Teste de ponta a ponta do ciclo "stall" com fakes |
| M5 | Export para o Anki + upload e URL assinada (com fake de storage nos testes) | O `.txt` bate byte a byte com o arquivo esperado |
| M6 | **Simulador de terminal** `python -m sim` (`ConsoleChannel` + `MemoryRepository`; `--real-llm` opcional) | Consigo fazer o ciclo completo no terminal |
| M7 | `docker-compose.yml` (waha + bot), `infra/` (seção 10), README com o runbook | `docker compose config` válido; scripts passam em `bash -n` e `shellcheck`; nenhum segredo versionado |
| M8 | Provisionar e fazer o deploy na VM, comigo aprovando cada comando; parear o WhatsApp; smoke test | O WAHA está em `WORKING` e o bot responde `/ajuda` no WhatsApp |

**Opcional antes do M8:** subir o compose localmente (`docker compose up`) e parear um teste no próprio computador. Se fizer isso, use um volume de sessão separado, porque o número só pode ter uma sessão do WAHA ativa por vez.

## 10. Infraestrutura (GCP)

Pré-requisitos, que eu garanto: `gcloud` autenticado, projeto definido, faturamento ativo (trial) e papel de Owner.

### 10.1 `infra/config.sh` + `infra/.env.infra` (no `.gitignore`, com `.env.infra.example`)
Contém `GCP_PROJECT_ID` (lido do `.env.infra`; se vazio, de `gcloud config get-value project`), `REGION=us-central1`, `ZONE=us-central1-a`, `VM_NAME=vocabot-vm`, `SA_NAME=vocabot-vm`, `EXPORT_BUCKET=${PROJECT_ID}-vocabot-exports` e os valores não secretos da seção 4.

Exemplo de `infra/.env.infra.example`:
```dotenv
GCP_PROJECT_ID=
ALLOWED_NUMBER=      # número pessoal do usuário, só dígitos (quem conversa com o bot)
BOT_NUMBER=          # número Vivo do bot, só dígitos
LLM_PROVIDER=vertex_gemini
GEMINI_MODEL=        # preencher com o ID confirmado na documentação
GEMINI_MODEL_EVAL=
VERTEX_LOCATION=global
USER_LEVEL=B1-B2
PRACTICE_MODE=guiado
```

### 10.2 `infra/setup.sh` (idempotente)
1. Ativar as APIs `compute`, `firestore`, `secretmanager`, `storage`, `iap`, `iamcredentials`, `logging` e **`aiplatform`** (Vertex AI).
2. Criar o Firestore nativo em `us-central1` e a política de TTL em `processed.expira_em`.
3. Criar a conta de serviço `vocabot-vm` com os papéis `roles/datastore.user`, `roles/secretmanager.secretAccessor`, `roles/logging.logWriter` e **`roles/aiplatform.user`**. Adicionar `roles/iam.serviceAccountTokenCreator` **na própria SA** e `roles/storage.objectAdmin` **só no bucket**.
4. Criar o bucket (`us-central1`, *uniform access*, prevenção de acesso público) com ciclo de vida de 7 dias.
5. Criar os segredos. `WAHA_API_KEY` e `WAHA_DASHBOARD_PASSWORD` são gerados com `openssl rand -hex 24` e enviados por pipe, sem ecoar na tela. `ANTHROPIC_API_KEY` só é criado (sem versão) se `LLM_PROVIDER=anthropic`.
6. Criar a regra de firewall `allow-iap-ssh` (tcp:22 a partir de `35.235.240.0/20`, só para a tag `vocabot`). **Não** abrir as portas 3000 ou 8000.
7. Criar a VM, se não existir:
   - `e2-micro`, `us-central1-a`, Debian 12;
   - boot disk `pd-standard` de 30 GB;
   - SA `vocabot-vm` com escopo `cloud-platform`, tag `vocabot`;
   - IP externo efêmero (necessário para saída à internet) e network tier `STANDARD`;
   - `--metadata-from-file startup-script=infra/vm/startup.sh`.
8. `infra/vm/startup.sh` (idempotente, roda a cada boot): instala o Docker Engine e o plugin compose (se faltar), cria o swap de 2 GB (se faltar), cria `/opt/vocabot` e ativa o Docker no boot.

### 10.3 `infra/secrets.sh` (opcional; quem roda sou eu, em outro terminal)
Só é necessário com `LLM_PROVIDER=anthropic`. Pergunta `ANTHROPIC_API_KEY` com `read -rsp` e adiciona uma versão (`printf '%s' | gcloud secrets versions add --data-file=-`). Oferece pular se já existir.

### 10.4 `infra/deploy.sh`
1. Empacotar o repo (`git archive` ou `tar`, sem `.git`, `.env*`, `tests/` e `evals/`) e copiar para a VM (`gcloud compute scp --tunnel-through-iap`).
2. Na VM, por ssh:
   - extrair em `/opt/vocabot/app`;
   - **renderizar `/opt/vocabot/.env`** com `gcloud secrets versions access latest` para cada segredo, mais os valores não secretos, com `umask 077`;
   - rodar `docker compose up -d --build`.
3. Mostrar `docker compose ps` e as últimas linhas de log (filtrando nada sensível).

### 10.5 `infra/pair.sh`
Abre um túnel `gcloud compute ssh ... --tunnel-through-iap -- -N -L 3000:localhost:3000` e mostra as instruções:
1. abrir `http://localhost:3000/dashboard`;
2. entrar com `admin` e a senha do painel;
3. iniciar ou abrir a sessão `default` e escanear o QR com o app **WhatsApp Business** do número Vivo (Aparelhos conectados → Conectar um aparelho).

Mostre também como ver a senha do painel **localmente e só quando eu pedir** (`gcloud secrets versions access latest --secret=WAHA_DASHBOARD_PASSWORD`), rodado por mim.

### 10.6 Utilitários
- `infra/logs.sh`: `docker compose logs -f --tail=200`.
- `infra/ssh.sh`: abre um ssh via IAP.
- `infra/smoke_test.sh`: pela VM, testa `GET /health` do bot e verifica se a sessão do WAHA está `WORKING`.

### 10.7 `docker-compose.yml`
- `waha`:
  - imagem Core com **tag fixada**, engine `GOWS`;
  - volume `waha_sessions` na pasta de sessões;
  - API key e credenciais do painel vindas do `.env`;
  - webhook para `http://bot:8000/waha/webhook` com os eventos `message` e `session.status`;
  - reinício automático das sessões ao subir;
  - porta publicada **só em `127.0.0.1:3000`** (para o túnel);
  - `restart: unless-stopped`, `mem_limit: 400m`.
- `bot`:
  - build local, `env_file: /opt/vocabot/.env`, sem portas publicadas;
  - healthcheck em `/health`;
  - `restart: unless-stopped`, `mem_limit: 300m`.

### 10.8 Custos (para você respeitar)
A VM `e2-micro` com disco standard de 30 GB em `us-central1` está no nível gratuito. O Gemini no Vertex AI é pago por uso (centavos neste volume), coberto pelos créditos do trial. Os créditos do trial **não** pagam modelos de parceiros (ex.: Claude no Vertex), por isso ele não é opção aqui. O IP externo **não** está: custa alguns dólares por mês, coberto pelos créditos do trial. Firestore, Storage e Secret Manager ficam nas cotas gratuitas. Não crie Cloud NAT, balanceador, IP estático reservado nem máquinas maiores.

## 11. Estrutura esperada
```
vocabot/
  CLAUDE.md  README.md  pyproject.toml  Dockerfile  docker-compose.yml
  .dockerignore  .gitignore  .env.example
  app/
    main.py  config.py  messages.py
    channel/  base.py  waha.py  console.py  parser.py
    domain/   models.py  state.py  choices.py
    flows/    router.py  capture.py  practice.py  expansion.py  commands.py
    services/ llm.py  prompts.py  anki.py  storage.py
    repo/     base.py  memory.py  firestore.py
  sim/        __main__.py
  evals/      sentencas.yaml  run.py
  infra/      config.sh  setup.sh  secrets.sh  deploy.sh  pair.sh  logs.sh  ssh.sh  smoke_test.sh
              .env.infra.example  vm/startup.sh
  tests/      fixtures/*.json  test_*.py
  docs/adr/   README.md  0000-template.md  NNNN-*.md
```
Se existir `referencia/`, ela contém um MVP anterior, feito para a Cloud API oficial (webhook da Meta, export etc.). Use-a só como consulta: o canal agora é o WAHA.
