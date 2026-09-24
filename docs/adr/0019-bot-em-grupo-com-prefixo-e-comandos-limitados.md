# ADR-0019: Bot em grupo com prefixo `!` e comandos limitados

- **Status:** Aceito
- **Data:** 2026-09-24

## Contexto

O piloto é um cursinho de inglês com turmas de 2 a 5 alunos, com aula semanal. Durante a aula
aparecem palavras e expressões novas; a ideia é a turma (alunos e professores) salvá-las num grupo de
WhatsApp com o bot, praticar ali mesmo e discutir. **A discussão entre os alunos no grupo é parte do
objetivo**, então o bot não pode ser um assistente que responde a tudo, nem ler a conversa toda.

No privado, uma palavra sem prefixo é uma palavra nova, e os comandos levam `/`. No grupo isso não
funciona: qualquer frase da conversa seria interpretada como palavra.

## Decisão

- **Só o prefixo chama o bot.** Em grupo ativo (ADR-0018), uma mensagem que não começa com o prefixo
  (`GROUP_PREFIX`, padrão `!`) é descartada no webhook antes da deduplicação e do `sendSeen`, sem
  gravar nada e sem logar o conteúdo. `!` sem letra ou número logo depois (`!!!`, `! `) também é
  conversa. Mídia em grupo é ignorada em silêncio.
- **Conjunto fechado de comandos**, tirado o prefixo: `add`, `list`, `practice`, `review`,
  `reminder`/`reminders`, `group`, `help` (mais `teacher`/`student`, escondidos do `help`, e
  `activate`/`deactivate` do ADR-0018). `!add` é a **única** forma de trazer uma palavra nova.
- **Dentro de uma atividade**, `!1`, `!2`, `!3` e `!texto` são as respostas, entregues à mesma máquina
  de estados do privado (`AWAIT_ACTION`, `REVIEWING`). No roteamento livre, um `nova_palavra` no grupo
  só devolve a dica de `!add`. Fora de atividade, qualquer outra coisa recebe a ajuda do grupo,
  **sem chamar a IA**.
- **Comandos do privado no grupo** (`!export`, `!level`, `!song`...) recebem a ajuda do grupo, que
  nunca os cita. Com barra (`/list`), a mensagem nem é lida.
- **Papéis.** `espacos/{grupo}/membros/{numero}` com `{papel, nome}`. Quem manda a primeira mensagem
  com prefixo entra como `aluno`. `!teacher`/`!student` (um professor da turma ou o dono) mudam o
  papel; para os demais, o comando não existe. Sem nome do WhatsApp, o `!group` mostra "Student N",
  nunca o telefone.
- **Autoria.** `sentences.autor_id` guarda o número de quem escreveu a frase.
- **Textos.** Toda mensagem que cita comando recebe o prefixo do espaço (`/` no privado, o do grupo
  no grupo). No privado o texto é idêntico ao de antes; no grupo só se citam comandos do grupo.
- **Privado:** nada muda, e o prefixo do grupo é aceito como apelido escondido da barra (`!list` vale
  `/list`) se uma letra vem logo depois.
- O limite de "3 mensagens seguidas sem resposta" vale por espaço, e qualquer mensagem com prefixo, de
  qualquer participante, conta como resposta.
- Lembretes do grupo (`!reminder`) usam o mesmo agendador; um grupo desativado (ADR-0018) não recebe.

## Alternativas consideradas

- **Desenho híbrido (captura no grupo, prática no privado)** — descartado pelo usuário: a discussão
  entre os alunos no grupo é o objetivo.
- **Responder citando a mensagem do bot** — mais difícil de explicar aos alunos do que um prefixo.
- **Menção `@bot`** — depende de detectar a menção ao próprio bot (que pode ser um LID), mais frágil.
- **Prefixo `/` também no grupo** — descartado para não confundir com o conjunto de comandos do
  privado.
- **Todos os comandos do privado no grupo** — descartado para manter o grupo simples e o texto curto.

## Consequências

- **Privacidade:** o bot não processa conversa sem prefixo, nem a grava.
- Uma frase de prática que comece com o nome de um comando (`!list of things is long`) é lida como
  comando. É o preço de um conjunto de comandos pequeno e sem `!` extra para as respostas.
- O nome do membro vem do payload da mensagem (`_data.pushName`/`Info.PushName`), que a doc do WAHA
  não especifica: sem ele, os membros aparecem como "Student N". Os números mencionados em
  `!teacher @fulano` também dependem de um campo não documentado (`mentionedIds`); o número escrito
  no texto sempre funciona.
- O nível do grupo é o `USER_LEVEL` padrão: não há `!level` na turma (pendência).
- Quem manda `!` no grupo entra na lista de membros, mas quem nunca escreveu com prefixo não aparece
  no `!group`.
