# CLAUDE.md — Vocabot (MVP, versão WAHA + Gemini no Vertex AI)

Este arquivo é a especificação do projeto. Leia-o inteiro antes de escrever código. Trabalhe **marco a marco** (seção 9), pare ao fim de cada um para eu revisar e só avance quando eu aprovar.

---

## 1. O que estamos construindo

Um bot de WhatsApp, de uso pessoal e com um único usuário, para praticar vocabulário de inglês. O nível do usuário é **B1 indo para B2**, e ele é brasileiro. **M9:** a conversa do bot com o aluno é em inglês (imersão) — só a tradução literal do termo fica em PT-BR; esta especificação e o código continuam em PT-BR.

**Canal:** o bot tem um número próprio (chip Vivo) com o app **WhatsApp Business** instalado num celular. O servidor se conecta a esse número como **aparelho conectado** (linked device) usando o **WAHA Core** (WhatsApp HTTP API, self-hosted e gratuito). O usuário conversa com o bot a partir do WhatsApp pessoal dele. **Não** usamos a Cloud API oficial da Meta.

Ciclo principal:

1. O usuário manda uma palavra ou expressão em inglês, opcionalmente com a frase onde a viu (ex.: `stall | the talks stalled`).
2. O bot explica a palavra numa única mensagem (o "card"): tradução, definição curta, uma dica e uma frase de exemplo — a IA já escolhe o sentido mais provável, sem perguntar.
3. O card termina no **menu único**: 1 ver mais exemplos, 2 ver sinônimos, 3 só salvar — sempre com o convite a já escrever uma frase.
4. Texto livre (frase, pedido de ajuda, palavra nova, ou fora do escopo) é roteado por uma única chamada de IA (seção 5.1) que classifica e já responde. Frase de prática: avalia se usa a palavra corretamente, naquele sentido, e se é natural; o usuário pode tentar de novo.
5. Ao concluir, tudo fica salvo no Firestore: a palavra, o sentido, as frases do usuário com as avaliações e os exemplos.
6. Ao salvar ("3" ou pedido livre), o bot sugere até 3 **expressões relacionadas** como texto — sem menu; o usuário só manda a que quiser como qualquer palavra nova.
7. `/export` gera uma **planilha Excel** (`.xlsx`) com tudo o que foi coletado e **envia o arquivo direto no chat** (seção 7.3); só se o WhatsApp não aceitar, manda um **link temporário**. (Até o M11 era um `.txt` para o Anki; ver ADR-0014. O envio direto vem da ADR-0015: desde a 2026.6.1 o WAHA Core inclui os recursos do Plus, e o `/api/sendFile` deixou de ser exclusivo do Plus.)

**M10:** o bot também faz revisão espaçada com lembretes agendados (seção 5.7) — deixou de ser fora de escopo.

Fora de escopo no MVP: áudio, multiusuário, painel web e conversa livre com IA sem relação a inglês.

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
5. Todo texto voltado ao usuário fica em `app/messages.py`, **em inglês**, tom amigável e curto — só a linha 🇧🇷 (tradução literal) fica em PT-BR (M9).
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
| `WAHA_HOOK_HMAC_KEY` | Secret Manager (gerado) | Chave da assinatura HMAC dos webhooks (seção 8.1); opcional para o bot |
| `ALLOWED_NUMBER` | `.env.infra` | Número **pessoal** do usuário, só dígitos (ex.: `5531999998888`) |
| `BOT_NUMBER` | `.env.infra` | Número Vivo do bot, só dígitos (informativo/logs) |
| `WAHA_URL` | compose | `http://waha:3000` |
| `WAHA_SESSION` | compose | `default` |
| `EXPORT_BUCKET` | `.env.infra` | Nome do bucket de exportações |
| `ANTHROPIC_MODEL` | `.env.infra` (opcional) | Padrão `claude-haiku-4-5-20251001` |
| `USER_LEVEL` | `.env.infra` | Padrão `B1-B2` |
| `TIMEZONE` | `.env.infra` | Padrão `America/Sao_Paulo`; fuso para distribuir os lembretes (M10, seção 5.7) |
| `APP_ENV` | compose | `local` ou `prod` |

Para desenvolvimento local, use um `.env` (no `.gitignore`) com valores falsos. Os testes nunca dependem de credenciais reais. Para o simulador com IA real (`--real-llm`), use as credenciais locais do Google (`gcloud auth application-default login`), sem chave em arquivo.

## 5. Especificação funcional

### 5.1 Máquina de estados

A sessão fica num único documento `session/current`. Desde o M9 há só **dois estados e um único
menu de ações**: a IA assume o papel das heurísticas antigas (sentido ambíguo, "isso é uma frase
ou uma palavra nova?", menu de expansões numerado). As escolhas do menu continuam por **número**;
aceite também variações (`1`, `1.`, apelidos em inglês como `examples`, `save`).

```
IDLE          ── texto (não comando) ──▶ explicar (a IA sempre escolhe um sentido) ──▶ AWAIT_ACTION
AWAIT_ACTION  ── 1 "see more examples" ──▶ gerar exemplos   ──▶ AWAIT_ACTION
              ── 2 "check synonyms"    ──▶ gerar sinônimos  ──▶ AWAIT_ACTION
              ── 3 "just save"         ──▶ salvar e sugerir ──▶ IDLE
              ── qualquer outro texto  ──▶ rotear pela IA (abaixo) ──▶ AWAIT_ACTION (ou IDLE)
```

**Roteamento por IA (`Tutor.route`, ADR-0009):** todo texto livre em `AWAIT_ACTION` que não é uma
opção do menu vira **uma única chamada de IA** que classifica a intenção e já devolve a resposta
(nunca uma segunda chamada separada para avaliar/gerar):

- `frase` — o aluno tentou usar a palavra-alvo numa frase (mesmo com erro ou flexão diferente):
  avalia, com os mesmos campos de `evaluate`.
- `exemplos` / `sinonimos` — pedido de mais exemplos/sinônimos, com quantidade opcional (1 a 10,
  padrão 3; fora do intervalo é limitado pelo fluxo, nunca pela IA).
- `salvar` — equivalente a digitar "3".
- `nova_palavra` — o texto não é sobre a palavra-alvo atual e parece uma nova palavra/expressão em
  inglês: salva a atual silenciosamente (como em "3") e explica a nova, numa segunda mensagem.
- `pedido` — qualquer outro pedido sobre aprender inglês (pronúncia, outro sentido da palavra,
  exemplos numa área específica, dúvida de gramática...): a IA já escreve a resposta, em inglês.
- `fora_do_escopo` — nada relacionado a aprender inglês (small talk, outro assunto): a IA recusa
  gentilmente, em inglês.

Regras:

- **Sessão parada há mais de 3 horas** volta para IDLE, salvando o que houver.
- `/cancel` (ou `/cancelar`) volta a IDLE sem apagar o que já foi salvo.
- **Sempre** reenvie o menu de ações ao final de cada resposta em `AWAIT_ACTION` — inclusive nas
  respostas do roteamento livre (`pedido`, `fora_do_escopo`, avaliação de `frase`), exceto quando a
  resposta já é o card de uma palavra nova (`nova_palavra`).

### 5.2 Comandos

`/help`, `/list [página]`, `/info N|palavra`, `/pending`, `/practice [N|palavra]`, `/review`,
`/reminders [N [INICIOh-FIMh] | off]`, `/profile`, `/export`, `/delete N|palavra`,
`/level A2-B1|B1-B2|B2-C1`, `/cancel`, `/status`. Todos os nomes são em inglês (M12, ADR-0014). Os
apelidos em PT-BR que a spec sempre teve (`/ajuda`, `/lista`, `/pendentes`, `/praticar`,
`/exportar [tudo]`, `/apagar`, `/nivel`, `/cancelar`, `/reminders`, `/review`, `/perfil`)
**continuam funcionando, mas nenhuma mensagem do bot os divulga**.

- `/list` mostra as palavras **das mais novas para as mais antigas**, 20 por página: as mais
  novas ficam sempre na página 1, e `/list 2` é a página 2. Uma página inexistente responde com um
  aviso. Cada linha é `N. termo: tradução em PT-BR`, sem emoji de status (use `/pending` para ver as
  ainda não praticadas). O número de cada palavra é **fixo** (1 = a mais antiga, na ordem de criação), então
  `/info 7` e `/delete 7` continuam apontando para a mesma palavra quando entram palavras novas.
- `/info N` (número da `/list`) ou `/info palavra` mostra tudo de uma entrada: tradução, definição,
  outros sentidos, nota, status e próxima revisão, as frases do aluno **já corrigidas** (a
  `versao_natural`, sem `[[ ]]`, até 5, sem repetir), até 3 exemplos do bot e os sinônimos salvos.
  `/practice` e `/delete` também aceitam o número.
- `/pending` lista as entradas com status `nova`.
- `/export` gera a planilha com **todas** as palavras (ver 7.3); `/export all` (e `/exportar tudo`)
  é aceito e faz o mesmo. Sem nenhuma palavra, o bot avisa que não há o que exportar.
- `/practice` sem argumento pega a pendente mais antiga.
- `/level` aceita A2-B1, B1-B2 e B2-C1.
- `/reminders` e `/review`: ver seção 5.7.
- `/profile` mostra o nível, o total de palavras (praticadas e pendentes), quantas estão vencidas
  para revisão e os lembretes (`every day, 3x between 9h and 21h` ou `off`) e, com os lembretes ligados, **quando o
  próximo toca** (`Next reminder: today at 14:00`, `tomorrow at 08:00` ou `Mon 28 Sep at 08:00`, no
  fuso do aluno). `/reminders` (consulta e ao ligar/mudar) mostra o mesmo horário. O horário vem de
  `profile/me.proximo_lembrete` se ainda está no futuro; senão é calculado da janela
  (`app/domain/lembretes.py:proximo_a_exibir`). Os lembretes rodam todos os dias; não há escolha de
  dias da semana.
- `/status` mostra o status da sessão do WAHA, o total de palavras e as pendentes.

### 5.3 Calibração pelo nível (B1-B2)

- **Exemplos:** vocabulário de apoio no máximo B2 (a palavra-alvo pode ser de qualquer nível), 8 a 18 palavras por frase, contextos variados (empresa internacional, dia a dia, informal).
- **Avaliação:** tolerante com frases simples e corretas. Prioridade: sentido, depois gramática e colocação, depois naturalidade. Explicação em inglês, com no máximo 4 linhas (M9: só a linha 🇧🇷 do card fica em PT-BR).
- **Expansões:** colocações e expressões frequentes de nível B1-B2, ligadas ao sentido escolhido. Evite idiomatismos raros (C2).
- Cada entrada guarda `cefr_estimado`.

### 5.4 Menu único de prática (M9)

Não há mais modos (`guiado` / `producao_primeiro`): toda palavra cai no mesmo menu de ações
(seção 5.1), sempre com o convite a escrever uma frase junto — `Profile` não guarda mais `modo`.

### 5.5 Formato das mensagens

Use a formatação do WhatsApp (`*negrito*`, `_itálico_`) e emojis com moderação. Um único texto por
resposta sempre que possível. Desde o M9, **tudo em inglês** — só a linha 🇧🇷 (tradução literal)
fica em PT-BR — e o menu de ações (seção 5.1) termina praticamente toda resposta.

**Card inicial** (o aluno manda uma palavra; a IA já escolhe um sentido e gera uma frase de
exemplo calibrada, reaproveitando palavras que o aluno já salvou quando der):
```
*stall* (verb) — B2
🇧🇷 travar, emperrar; enrolar
📖 to stop making progress
💡 Think of a car engine that dies in traffic.
"The project [[stalled]] because the client didn't send the documents."

Now, you can write one or more sentences using *stall*, or type:
1️⃣ See more examples
2️⃣ Check synonyms
3️⃣ Just save
```

**Case A — texto livre** (roteado pela IA, seção 5.1). Frase de prática avaliada:
```
⚠️ *Almost there!* The meaning is right.
✏️ didn't sent → didn't send
✨ The project stalled because the client didn't send the documents.
💬 After "didn't", the verb stays in the base form.

Want to try another sentence?
Now, you can write one or more sentences using *stall*, or type:
1️⃣ See more examples
2️⃣ See more synonyms
3️⃣ Just save
```
Pedido de ajuda ou palavra fora do escopo: a resposta da IA (ou, fora do escopo, uma recusa
gentil) seguida do mesmo menu. Palavra nova: salva a atual silenciosamente e manda o card da nova,
como se fosse `IDLE`.

**Case B — "1" / "see more examples"** (padrão 3, máximo 10, sem repetir os já mostrados):
```
📝 *Examples with stall* (travar, emperrar)
1. We had to stall before the deadline.
2. She didn't want to stall in front of the client.
3. It's easy to stall when nobody is watching.

Want to try a sentence of your own?
Now, you can write one or more sentences using *stall*, or type:
1️⃣ See more examples
2️⃣ Check synonyms
3️⃣ Just save
```

**Case C — "2" / "check synonyms"** (padrão 3, máximo 10, sem repetir os já mostrados; a partir
daqui a opção 2 do menu vira "See more synonyms"):
```
🔄 *Synonyms for stall* (travar, emperrar)
*stumble* = to almost fail or lose momentum
_Example: "The talks stumbled early on."_

Want to try a sentence with *stall*?
Now, you can write one or more sentences using *stall*, or type:
1️⃣ See more examples
2️⃣ See more synonyms
3️⃣ Just save
```

**Case D — "3" / "just save"** (fecha a palavra; sugere até 3 expressões relacionadas só como
texto, sem criar entradas nem menu — se o aluno quiser uma, é só mandá-la como qualquer palavra
nova):
```
✅ Saved: *stall*.
Practice it any time with /practice stall, or see everything with /list.
You might like these too: *stall for time*, *grind to a halt*, *drag on*.
Send me another word or expression whenever you want.
```

### 5.6 Comportamento "humano" (reduz o risco de bloqueio)

- Marque as mensagens recebidas como lidas (`sendSeen`).
- Mostre "digitando…" (`startTyping`) enquanto chama a IA e pare antes de enviar.
- Espere de 1 a 2 s (aleatório) antes de cada envio.
- **Nunca** envie mensagem para número diferente do `ALLOWED_NUMBER`.
- Nunca mande mais de 3 mensagens seguidas sem uma resposta do usuário.

### 5.7 Revisão espaçada e lembretes (M10, ADR-0011, ADR-0012)

O bot também **inicia** conversas: no horário combinado, escolhe até 20 palavras vencidas e faz
uma sessão de revisão. Espaçamento estilo Anki (SM-2 simplificado, `app/domain/srs.py`), mas a
nota vem do julgamento da IA sobre a resposta em texto livre do aluno, não de 4 botões.

**Configuração:** `/reminders` mostra o estado; `/reminders N` liga N vezes por dia na janela
padrão (9h–21h); `/reminders N INICIOh-FIMh` usa uma janela própria (N de 1 a 8, `0 <= início <
fim <= 23`); `/reminders off` desliga. Desligado por padrão; a primeira palavra salva mostra uma
dica de uma linha sobre o comando, uma única vez. Os horários se distribuem igualmente dentro da
janela (`app/domain/lembretes.py:horarios_do_dia`).

**Máquina de estados:** um novo estado, `REVIEWING`. Durante ele, qualquer texto que não seja
"sair" (`0`, `stop`, `quit`, `exit`, `leave`) é a resposta à palavra atual — sem roteamento por IA
aqui (seria ambiguidade e custo à toa). Comandos (`/`) continuam funcionando; `/cancelar` fecha a
sessão com o resumo, como `0` faria.

```
⏰ *Practice time* — 12 words to review.

🔁 1/12 · *stall*
Explain it in English in your own words, or write a sentence using it.
_Type 0 to leave the practice._
```
Cada turno seguinte é **uma mensagem só**, com o feedback da resposta anterior e o próximo card
juntos (respeita o limite de 3 mensagens seguidas, seção 5.6):
```
✅ That's it — you clearly remember this one.
💬 "to stop making progress" is exactly the idea.

🔁 2/12 · *deadline*
Explain it in English in your own words, or write a sentence using it.
_Type 0 to leave the practice._
```
Ao acabar a fila, digitar `0` ou `/cancelar`:
```
🎉 *Practice done* — 9 of 12 reviewed.
✅ Solid: stall, deadline, overwhelmed
🔁 Coming back soon: reluctant, mitigate
Send me a new word or expression whenever you want.
```

**Fila de uma sessão** (`app/flows/review.py:montar_fila`): as vencidas primeiro (mais antiga
primeiro; `proxima_revisao=None` = cartão novo, vencido desde já), completando até 20 com as que
vencem mais cedo entre as que ainda não venceram. Sem nada vencido, o agendador fica em silêncio —
nunca manda "nada para revisar" sem o aluno pedir (só `/review`, chamado explicitamente, avisa).
Uma resposta `de_novo` volta a palavra para o **fim da fila desta sessão** (como no Anki) e conta
um lapso; as demais notas (`dificil`/`bom`/`facil`) avançam o agendamento.

**Disparo, com três camadas de segurança** (seção 5.6, ADR-0012): um agendador em segundo plano
(`app/services/lembretes.py:Agendador`), acordando a cada minuto. Só dispara com um `chat_id` real
— o número que o WhatsApp de fato usa para esse aluno, aprendido de uma mensagem recebida (nunca o
`ALLOWED_NUMBER` do `.env` direto: pode diferir no nono dígito, seção 8.2). Nunca dois lembretes
seguidos sem resposta ao anterior (`lembrete_sem_resposta`, limpo na próxima mensagem do aluno,
qualquer que seja). Se a conversa está aberta (`sessao.estado != IDLE`), adia para o próximo tick,
e desiste (recalculando o próximo horário) se o atraso passar de 2 horas.

`/review` começa a sessão na hora, sem esperar o próximo horário.

## 6. Contratos com a IA

Implemente em `app/services/llm.py` uma interface `LLMProvider` com duas implementações:

- `VertexGeminiProvider` (padrão): `google-genai` com `vertexai=True`, `project=GCP_PROJECT_ID` e `location=VERTEX_LOCATION`. Peça **saída estruturada** com o schema derivado do modelo Pydantic (JSON mode com schema), conforme a documentação atual da SDK para o modelo escolhido.
- `AnthropicProvider` (opcional): *tool use* com uma única ferramenta por tarefa (`input_schema` = schema Pydantic) e `tool_choice` forçando essa ferramenta.

As funções de negócio (`explain`, `evaluate`, `examples`, `expansions`, `synonyms`, `route`) não sabem qual provedor está em uso. Valide sempre com Pydantic, com 1 nova tentativa em caso de erro. Temperatura 0.2 a 0.3. Prompts em `app/services/prompts.py`, com o nível e o contexto do usuário ("brasileiro, trabalha numa empresa internacional, usa inglês técnico no dia a dia"). **M9:** toda saída voltada ao aluno é pedida em inglês — só `traducao` continua em português do Brasil.

```python
class Sense(BaseModel):
    id: str; traducao: str; definicao: str; exemplo: str  # exemplo: frase completa, alvo entre [[ ]]

class Explanation(BaseModel):
    ok: bool
    motivo_erro: str | None
    palavra: str                    # forma base, minúsculas
    classe: str                     # em inglês (verb, noun, adjective...)
    cefr_estimado: Literal["A2","B1","B2","C1","C2"]
    sentidos: list[Sense]           # 1 a 4, só os comuns
    sentido_do_contexto: str | None # M9: a IA sempre escolhe um id (nunca null)
    frase_contexto: str | None      # frase do usuário corrigida, alvo entre [[ ]]
    nota: str                       # em inglês
    tags: list[Literal["trabalho","phrasal_verb","expressao"]]

class Evaluation(BaseModel):
    usa_palavra_alvo: bool          # considera flexões
    sentido_correto: bool
    veredito: Literal["correta","correta_pouco_natural","quase","incorreta"]
    correcoes: list[str]            # "wrong → right"
    versao_natural: str             # alvo entre [[ ]]
    explicacao: str                 # em inglês, máx. 4 linhas

# examples(palavra, sentido, nivel, n=3, ja_mostrados, palavras_do_aluno) -> list[str]  (alvo entre [[ ]])

class Expansion(BaseModel):
    expressao: str; traducao: str
    tipo: Literal["colocacao","familia","phrasal_verb","sinonimo","expressao"]
# expansions(palavra, sentido, nivel, ja_existentes) -> list[Expansion]  (3 a 5, sem repetir o que já existe)
# Case D (seção 5.5) usa só as 3 primeiras, como sugestão em texto — não cria entradas.

class Synonym(BaseModel):
    expressao: str; significado: str; exemplo: str  # exemplo com o SINÔNIMO marcado entre [[ ]]
# synonyms(palavra, sentido, nivel, n=3, ja_mostrados) -> list[Synonym]  (1 a 10, sem repetir)

# Roteamento de texto livre (M9, ADR-0009): uma única chamada que classifica e já responde.
# Achatado de propósito (sem objeto aninhado opcional) para caber bem no response_schema do Gemini.
class Roteamento(BaseModel):
    intencao: Literal["frase","exemplos","sinonimos","salvar","nova_palavra","pedido","fora_do_escopo"]
    quantidade: int              # exemplos | sinonimos, padrão 3 (o fluxo limita a 1-10)
    palavra: str                 # nova_palavra
    resposta: str                # pedido | fora_do_escopo, em inglês
    # frase: os campos abaixo formam a mesma Evaluation de cima
    usa_palavra_alvo: bool; sentido_correto: bool; veredito: str
    correcoes: list[str]; versao_natural: str; explicacao: str
# route(palavra, sentido, texto, nivel) -> Roteamento

# Revisão espaçada (M10, seção 5.7, ADR-0011): julga a resposta livre do aluno numa revisão.
class Revisao(BaseModel):
    tipo: Literal["definicao","frase","nao_sei","outro"]
    qualidade: Literal["de_novo","dificil","bom","facil"]
    feedback: str        # em inglês, máx. 4 linhas
    correcao: str         # só quando ajuda (qualidade != "facil"); vazio senão
# review(palavra, sentido, resposta, nivel) -> Revisao
```

**Qualidade:** `evals/sentencas.yaml` (~15 casos de frase + veredito esperado) e `evals/roteamento.yaml`
(um caso por intenção do `Roteamento`), medidos com `python -m evals.run [--tarefa avaliacao|roteamento] [--provider vertex_gemini|anthropic] [--model ID]` contra a API real. Assim comparo modelos antes de escolher. Fica fora do pytest.

## 7. Dados

### 7.1 Firestore
```
profile/me                 { nivel, criado_em,
                             lembretes_por_dia, janela_inicio, janela_fim, chat_id?,
                             proximo_lembrete?, lembrete_sem_resposta, avisou_lembretes }
                           # M10 (seção 5.7): lembretes_por_dia=0 é desligado (padrão); chat_id é o
                           # destino real, aprendido de uma mensagem recebida (nunca o .env direto)
session/current            { estado, entry_id, sentido_id, sinonimos_mostrados, atualizado_em,
                             revisao_fila, revisao_atual?, revisao_feitas, revisao_lapsos, revisao_total }
                           # M9: sinonimos_mostrados evita repetir e troca o rótulo do menu
                           # ("Check synonyms" -> "See more synonyms") depois da 1ª vez
                           # M10: os 5 campos de revisao_* só valem com estado=REVIEWING
entries/{slug}             { palavra, classe, cefr_estimado, sentido:{traducao,definicao}, outros_sentidos,
                             sinonimos, nota, tags, origem_texto, origem:"usuario"|"expansao", pai?, status:"nova"|"praticada",
                             exportado, criado_em, atualizado_em,
                             repeticoes, intervalo_dias, facilidade, lapsos, proxima_revisao?, revisada_em? }
                           # M12: sinonimos = [{expressao, significado, exemplo}] já mostrados ao aluno
                           # M10: campos de SM-2 simplificado (ADR-0011); proxima_revisao=None
                           # é um cartão novo, vencido desde já
entries/{slug}/sentences/{auto}  { texto, autor:"usuario"|"bot", veredito?, correcoes?, versao_natural?, explicacao?, criado_em }
                           # M12: versao_natural é a frase do aluno já corrigida pela IA (também nas revisões)
processed/{message_id}     { criado_em, expira_em }     # deduplicação; política de TTL de 7 dias
lids/{lid}                 { numero }                   # cache LID -> número (seção 8.2), evita consultar o WAHA a cada mensagem
```
- `slug`: minúsculas, `[^a-z0-9]+` → `-`. Se o mesmo slug surgir com outro sentido, use o sufixo `--s2`.
- Defina a interface `Repository` (Protocol) com `FirestoreRepository` e `MemoryRepository`. A deduplicação usa `create()`, que falha se o ID já existe.

### 7.2 Status e frase do cartão
- Uma entrada fica `praticada` quando tem ao menos uma frase do usuário avaliada; senão, é `nova`.
- A frase do cartão é a melhor frase **do usuário** (`correta`, senão a `versao_natural` mais recente). Se não houver, use o primeiro exemplo do bot.

### 7.3 Export em planilha Excel (M12, ADR-0014)
`/export` gera um `.xlsx` (openpyxl) com **todas** as palavras, em três abas. Cabeçalho em negrito e
congelado; datas em UTC, sem fuso (o Excel não guarda fuso).
- **Words** (uma linha por entrada): `#`, `Word`, `Class`, `CEFR`, `Translation`, `Definition`,
  `Other senses`, `Note`, `Tags`, `Status`, `Source text`, `Best sentence`, `Created`, `Last review`,
  `Next review`, `Repetitions`, `Lapses`, `Ease`. `Best sentence` segue a regra da seção 7.2, sem `[[ ]]`.
- **Sentences** (uma linha por frase, do aluno e do bot): `#`, `Word`, `Author` (`you`|`bot`),
  `Sentence`, `Corrected version`, `Verdict`, `Corrections`, `Explanation`, `Date`.
- **Synonyms**: `#`, `Word`, `Synonym`, `Meaning`, `Example`.

O campo `exportado` das entradas deixou de ser usado (a planilha é sempre um retrato completo).

**Entrega (ADR-0015):** o bot envia o `.xlsx` direto no chat, como documento, com uma legenda curta
(`Channel.send_file`, `POST /api/sendFile` com o arquivo em base64). Sem texto separado e sem link.
**Plano B:** se o envio falhar, o bot sobe o mesmo arquivo no bucket e manda o link. O upload em `gs://$EXPORT_BUCKET/exports/vocabot_AAAA-MM-DD_HHMM.xlsx` (hora em UTC), com
content-type `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`, e **URL assinada V4
válida por 24 h**. Na VM não há chave privada, então assine via IAM `signBlob`: a conta de serviço da
VM precisa do papel `roles/iam.serviceAccountTokenCreator` **sobre ela mesma**, e use
`service_account_email` + `access_token` no `generate_signed_url`. O bucket tem uma regra de ciclo de
vida que apaga objetos após 7 dias.

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
- **Envie sempre para o chatId do remetente autorizado**: o número que o WhatsApp informa (`NUMERO@c.us`, ou o `pn` resolvido do LID), nunca para outro chat. Ele bate com o `ALLOWED_NUMBER` a menos do nono dígito brasileiro: contas antigas são registradas **sem** o 9, e enviar para o número com o 9 falha no WAHA com "no LID found" (visto no deploy real).

### 8.3 Cliente (`app/channel/waha.py`)
Implemente `send_text`, `send_file`, `send_seen`, `typing(on/off)` e `session_status`, com o header `X-Api-Key` (ou o nome atual segundo a documentação). Timeouts de 15 s, até 2 novas tentativas com backoff para 5xx, logs **sem** a API key. `send_file` é a exceção: timeout de 90 s e **sem** retentativa (reenviar uma resposta lenta duplicaria o arquivo; quem chama decide o plano B).

### 8.4 Adaptador de canal
Crie a interface `Channel` (enviar texto, enviar arquivo, marcar como lido, digitando) com as implementações `WahaChannel`, `ConsoleChannel` (simulador) e `FakeChannel` (testes). A lógica de negócio **não** pode importar nada do WAHA diretamente, para que seja possível trocar por Cloud API ou Telegram no futuro.

## 9. Marcos (pare ao fim de cada um)

| # | Entrega | Critério de aceite |
|---|---|---|
| M0 | Estrutura do repo, dependências, ruff, pytest, `.gitignore`, `.dockerignore`, `Dockerfile` do bot, `.env.example` | `pytest` e `ruff check` passam |
| M1 | `main.py` (webhook do WAHA, health), parser de eventos, allowlist com LID, deduplicação, cliente WAHA, interface `Channel` | Testes com payloads de exemplo em `tests/fixtures/`: texto, `fromMe`, grupo, mídia, número não autorizado, LID, duplicado, `session.status` |
| M2 | Modelos, `Repository` (memória e Firestore), máquina de estados, parser de escolhas numéricas | Testes de todas as transições da seção 5.1, incluindo os atalhos |
| M3 | `llm.py`, `prompts.py`, schemas, `FakeLLM`, `evals/` | Testes com o fake; `python -m evals.run` funciona se houver chave |
| M4 | Fluxos e comandos completos | Teste de ponta a ponta do ciclo "stall" com fakes |
| M5 | Export para o Anki + upload e URL assinada (com fake de storage nos testes) | O `.txt` bate byte a byte com o arquivo esperado (substituído pelo Excel no M12) |
| M6 | **Simulador de terminal** `python -m sim` (`ConsoleChannel` + `MemoryRepository`; `--real-llm` opcional) | Consigo fazer o ciclo completo no terminal |
| M7 | `docker-compose.yml` (waha + bot), `infra/` (seção 10), README com o runbook | `docker compose config` válido; scripts passam em `bash -n` e `shellcheck`; nenhum segredo versionado |
| M8 | Provisionar e fazer o deploy na VM, comigo aprovando cada comando; parear o WhatsApp; smoke test | O WAHA está em `WORKING` e o bot responde `/ajuda` no WhatsApp |
| M9 | Interface em inglês (só 🇧🇷 em PT-BR), máquina de estados reduzida a `IDLE`/`AWAIT_ACTION` com um único menu de ações, roteamento de texto livre por uma chamada de IA (`Tutor.route`, ADR-0009), sinônimos (`Tutor.synonyms`), expansões viram sugestão em texto (sem menu) | `make check` passa; ciclo completo no `sim` bate a seção 5.5; `python -m evals.run --tarefa roteamento` roda contra a API real |
| M10 | Revisão espaçada (SM-2 simplificado, ADR-0011) com sessão `REVIEWING`, `/reminders` e `/review`, agendador em segundo plano (`Agendador`, ADR-0012) | `make check` passa; `make test-emulador` valida os campos novos no Firestore real; ciclo completo de revisão no `sim`; nenhum lembrete dispara sem `chat_id` conhecido |
| M12 | Comandos em inglês (apelidos PT escondidos), `/list` numerado e paginado, `/info`, `/profile`, sinônimos e frases corrigidas persistidos na entrada, `/export` em planilha Excel no lugar do arquivo do Anki (ADR-0014) | `make check` passa; `make test-emulador` valida `sinonimos` no Firestore real; `/export` no `sim` gera um `.xlsx` com as 3 abas |
| M11 | Deploy contínuo via GitHub Actions (seção 10.9, ADR-0013): branch protection na `main` (PR + checks obrigatórios), job `deploy` automático no merge, autenticado por Workload Identity Federation | Push direto na `main` é bloqueado pelo GitHub; um PR com CI verde, ao ser mergeado, dispara o job `deploy` e o bot responde `/help` depois do smoke test |

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
```

### 10.2 `infra/setup.sh` (idempotente)
1. Ativar as APIs `compute`, `firestore`, `secretmanager`, `storage`, `iap`, `iamcredentials`, `logging` e **`aiplatform`** (Vertex AI).
2. Criar o Firestore nativo em `us-central1` e a política de TTL em `processed.expira_em`.
3. Criar a conta de serviço `vocabot-vm` com os papéis `roles/datastore.user`, `roles/secretmanager.secretAccessor`, `roles/logging.logWriter` e **`roles/aiplatform.user`**. Adicionar `roles/iam.serviceAccountTokenCreator` **na própria SA** (ADR-0007: o `secretAccessor` é concedido em cada segredo, não no projeto) e `roles/storage.objectAdmin` **só no bucket**.
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
  - imagem com **tag fixada**, engine `GOWS` (hoje `devlikeapro/waha:gows-2026.8.2`; desde a 2026.6.1 o WAHA não separa mais Core/Plus);
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

### 10.9 Deploy contínuo via GitHub Actions (M11, ADR-0013)

O repositório é público: `pull_request` de fora roda sem segredo (padrão do GitHub), e log de
Action é visível a qualquer pessoa — nada sensível pode aparecer em log.

- **Branch protection na `main`:** exige PR (sem push direto) e os checks `checks`, `test` e
  `compose` do `ci.yml` como obrigatórios.
- **`infra/setup_cicd.sh`** (idempotente, mesmo padrão de `setup.sh`): cria o Workload Identity
  Pool (`github-pool`) e o provider OIDC (`github-provider`, emissor
  `token.actions.githubusercontent.com`, *attribute condition* travada em
  `assertion.repository == 'AndreMartins21/anki-whatsapp' && assertion.ref == 'refs/heads/main'`);
  cria a conta de serviço `vocabot-deploy` e concede `roles/compute.osAdminLogin` **só na instância
  da VM**, mais `roles/iap.tunnelResourceAccessor` e `roles/compute.viewer` **no projeto** (nenhum
  dos dois funciona só na instância — `gcloud` rejeita o primeiro e o segundo falha o deploy real
  porque `compute.projects.get` só existe no escopo do projeto; como só existe uma VM neste
  projeto, na prática já fica restrito a ela — ver ADR-0013) e `roles/iam.serviceAccountUser` só
  sobre a `vocabot-vm` (sem ele o SSH falha com `actAs`). Não concede nada direto em Secret
  Manager, Firestore, Storage ou Vertex — quem lê segredo continua sendo a VM —, mas root na VM
  mais `serviceAccountUser` alcançam tudo que a `vocabot-vm` alcança: a proteção da `main` e a
  attribute condition são a defesa real (ADR-0013).
- **Job `deploy` em `.github/workflows/ci.yml`:** `needs: [checks, test, compose]`, só roda em
  `push` para `main`; autentica via `google-github-actions/auth` (WIF, sem chave), roda
  `infra/deploy.sh` e depois `infra/smoke_test.sh` — se o smoke test falhar, o workflow fica
  vermelho.
- **Configuração no GitHub** (Settings → Secrets and variables → Actions): `ALLOWED_NUMBER` e
  `BOT_NUMBER` como **Secrets** (são telefone real, mascarados em log mesmo não sendo credencial);
  `GCP_PROJECT_ID`, `GCP_WIF_PROVIDER`, `LLM_PROVIDER`, `GEMINI_MODEL`, `GEMINI_MODEL_EVAL`,
  `USER_LEVEL`, `TIMEZONE` como **Variables**.
- Decisão do usuário (2026-09-23): sem gate de aprovação manual entre o merge e o deploy — o CI é a
  barreira de qualidade. Ver ADR-0013 para as alternativas descartadas.

## 11. Estrutura esperada
```
vocabot/
  CLAUDE.md  README.md  pyproject.toml  Dockerfile  docker-compose.yml
  .dockerignore  .gitignore  .env.example
  app/
    main.py  config.py  messages.py
    channel/  base.py  waha.py  console.py  parser.py
    domain/   models.py  state.py  choices.py  srs.py  lembretes.py
    flows/    router.py  capture.py  practice.py  expansion.py  synonyms.py  freeform.py  review.py  commands.py
    services/ llm.py  prompts.py  planilha.py  storage.py  lembretes.py
    repo/     base.py  memory.py  firestore.py
  sim/        __main__.py  tutor.py
  evals/      sentencas.yaml  roteamento.yaml  run.py
  infra/      config.sh  setup.sh  secrets.sh  deploy.sh  pair.sh  logs.sh  ssh.sh  smoke_test.sh
              .env.infra.example  vm/startup.sh
  tests/      fixtures/*.json  test_*.py
  docs/adr/   README.md  0000-template.md  NNNN-*.md
```
Se existir `referencia/`, ela contém um MVP anterior, feito para a Cloud API oficial (webhook da Meta, export etc.). Use-a só como consulta: o canal agora é o WAHA.
