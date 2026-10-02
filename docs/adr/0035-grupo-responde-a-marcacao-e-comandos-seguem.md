# ADR-0035: No grupo o bot responde a quem o marca; comandos seguem com `!` ou `/`

- **Status:** Aceito
- **Data:** 2026-10-02

## Contexto

O ADR-0019 fez do prefixo `!` o único jeito de chamar o bot em grupo, inclusive para responder: na
revisão, no desafio semanal e no menu da palavra, a resposta era `!texto`. Na prática o `!` na frente
de cada frase atrapalha (é o que o aluno mais esquece e parece um comando, não uma conversa), e a
turma já sabe marcar alguém no WhatsApp. O ADR-0019 descartou a marcação (`@bot`) por depender de
detectar o próprio bot (que pode ser um LID); hoje o webhook já resolve LID por número (`lids/`) e já
lê `mentionedIds` para o `!teacher`.

No desafio semanal (ADR-0034) o avaliador também cobrava o uso do vocabulário em destaque: uma resposta
boa que não usava as palavras caía para `dificil`.

## Decisão

1. **Conversa por marcação.** Em grupo ativo, uma mensagem que **marca o bot** é conversa com ele e vai,
   sem a marcação, para a mesma máquina de estados do privado: dentro de uma atividade é a resposta
   (`@bot 2`, `@bot a frase`, `@bot skip`); fora dela, `@bot stall` ou `@bot stall | contexto` adiciona
   a palavra (roteamento do ADR-0009) e `@bot` sozinho ou `@bot help` mostra a ajuda. Sem comando.
2. **Detecção da marcação** (`_sem_marcacao_do_bot`, no webhook): o número do bot (`BOT_NUMBER`, nono
   dígito à parte) em `mentionedIds` (número ou LID, resolvido pelo cache `lids/`) ou, como plano B,
   escrito no texto como `@numero`. Tira-se do texto só a marcação do bot (e do LID dele); a de outras
   pessoas fica. Marcar o bot e escrever um comando (`@bot !list`) vale como o comando.
3. **Comandos continuam, com `!` ou `/`.** O conjunto fechado do ADR-0019 vale com os dois prefixos
   (substitui as exceções `/skip`, `/1`... do ADR-0033): configurações (`level`, `daily`, `weekly`,
   `group`, `help`), `list`, `delete`, `practice`, `review`, `teacher`/`student`, `activate`. `!add`
   segue funcionando, escondido da ajuda: palavra nova entra marcando o bot. Dentro de uma atividade
   `!1`, `!skip` e `!texto` seguem como respostas.
4. **O resto é conversa entre pessoas**: sem marcação e sem comando, o bot não lê, não grava e não
   marca como lido (mesmo filtro, antes da deduplicação). Marcar **outra pessoa** não chama o bot.
5. **Avaliação do desafio semanal por coerência.** `weekly_answer` julga se a resposta é coerente com a
   pergunta no geral; usar as palavras do vocabulário **não é exigido** nem pesa para baixo (só
   melhora a resposta; no máximo o feedback sugere uma delas).
6. **Textos.** Menus e cartões do grupo mandam "marcar o bot" (`tag me`) no lugar de `!2`/"start with !".

## Alternativas consideradas

- **Responder citando a mensagem do bot** — descartada: depende do campo de citação do WAHA, ainda
  menos documentado que `mentionedIds`.
- **Manter o `!` também para responder** — descartada pelo usuário: é o que se quer tirar.
- **Tirar `!add`** — descartada: custa nada manter e protege quem já usa; só sai da ajuda.
- **Pedir ao WAHA o id do bot (`/api/sessions/{session}` -> `me`)** — descartada por ora: o número do
  `.env` mais o cache de LIDs já bastam e não dependem de campo não documentado; revisitar se a
  marcação por LID falhar no WhatsApp real.

## Consequências

- **Depende de `mentionedIds`**, que o WAHA não documenta (ver `docs/noite/PENDENCIAS.md`): se a
  marcação do bot vier só como `@<LID>` digitado e o LID não resolver, a mensagem é lida como conversa
  (o bot fica mudo). O plano B do texto com `@numero` só cobre quem marcou pelo número.
- Resolver LIDs agora acontece para toda mensagem de grupo que marca alguém (uma ida ao cache; só
  ao WAHA na primeira vez); mensagens sem nenhuma marcação continuam sem custo.
- O ADR-0019 segue valendo no resto (conjunto fechado de comandos, papéis, autoria, privacidade); só
  a regra "só o prefixo chama o bot" muda. O ADR-0033 deixa de precisar da lista `/skip`... (agora
  qualquer comando vale com `/`).
- A "frase que começa com nome de comando" do ADR-0019 deixa de ser problema: a resposta é marcada.
