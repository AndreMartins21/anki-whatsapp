# ADR-0020: Revisão em grupo com menção em rodízio

- **Status:** Aceito
- **Data:** 2026-09-24

## Contexto

No privado a revisão espaçada (ADR-0011) é de um aluno só: o bot manda uma palavra, a pessoa
responde, o cartão é dela. Numa turma de 2 a 5 alunos, o cartão é do **grupo** (as palavras são da
turma, ADR-0017), mas quem responde? Se qualquer um pode, o mais rápido responde sempre; se ninguém
é chamado, ninguém responde. A discussão entre os alunos é parte do objetivo, então o bot também
não pode calar quem quer comentar.

## Decisão

- **Cada card marca UM aluno**, com uma menção real do WhatsApp (`sendText` com `mentions`; o texto
  leva `@numero`). A escolha é um **rodízio** (`domain/rodizio.py`, função pura): quem foi marcado
  há mais tempo, ou nunca, vem primeiro; empate se resolve por sorteio; ninguém é marcado duas vezes
  seguidas se houver outro aluno. **Professores e o próprio bot nunca são marcados.**
- **Quem é aluno elegível:** quem está no grupo (`GET /groups/{id}/participants/v2`, atualizado no
  início de cada rodada) sem o bot e sem os professores. Quem está no grupo e nunca escreveu com
  prefixo entra no cadastro como aluno. Se o WAHA falha (ou devolve lista vazia), vale o cadastro de
  `membros/`. Sem nenhum aluno, a rodada não começa: o lembrete agendado fica em silêncio e o
  `!review` explica.
- **Rodada curta:** `LIMITE_POR_SESSAO_GRUPO` (5) palavras, contra 20 no privado.
- **Responder:** `!` + texto. Da pessoa marcada, vale a nota (`Tutor.review` julga, `srs.reagendar`
  atualiza o cartão do grupo), e o bot manda o feedback junto com o próximo card, numa mensagem só.
  De outra pessoa (aluno ou professor), o bot dá feedback, mas **não** muda a nota nem avança o
  card; a frase fica salva com o autor. `!0`/`!stop` de qualquer participante fecha com o resumo.
  Durante a revisão só `!0`, `!stop` e `!help` escapam da resposta.
- **Timeout:** se a pessoa marcada não responde em `TIMEOUT_MARCACAO_HORAS` (3), o agendador passa
  **o mesmo card** ao próximo aluno do rodízio, uma vez; se ninguém responde de novo, fecha a rodada
  com o resumo. O prazo (`Sessao.marcacao_expira_em`) é espelhado no documento do grupo
  (`timeout_em`), então o agendador acha os grupos vencidos com **uma consulta por tick**, sem ler
  os demais. O limite de "3 mensagens seguidas" é respeitado (card, repasse, fechamento).
- **Registro de participação:** `espacos/{grupo}/respostas/{auto}` com
  `{entry, autor_id, marcado, qualidade, criado_em}`. Não entra no agendamento; alimenta o `!group`
  (respostas por pessoa) e as métricas do piloto.

## Alternativas consideradas

- **Sorteio puro** — pode marcar a mesma pessoa várias vezes seguidas, e com 3 alunos isso é
  perceptível.
- **Qualquer um responde** — quem é mais rápido responde sempre, e os outros só assistem.
- **Agendamento por aluno dentro do grupo** (cada um com o próprio cartão) — complexo demais para o
  piloto de um mês, e perde a ideia de a turma estudar as mesmas palavras.

## Consequências

- **Limitação assumida:** a revisão do grupo é a "média da turma" só no sentido de que o cartão é do
  grupo e a nota vem de quem foi marcado. Um aluno pode saber a palavra e não ser marcado; o rodízio
  distribui as palavras entre os alunos com o tempo, mas a nota de um cartão nunca representa a turma
  inteira.
- A marcação usa o número em `@c.us`. Num grupo em que os participantes aparecem como LID, a menção
  pode não notificar a pessoa: só se confirma no WhatsApp real (ver `docs/noite/PENDENCIAS.md`).
- Se a pessoa marcada some e ninguém mais responde, a rodada fecha sozinha em até 6 horas, sem
  deixar uma sessão aberta para sempre.
- Lembretes do grupo (`!reminder`) reaproveitam o mesmo agendador do privado, com uma rodada de 5.
- Um lembrete que não acha aluno para marcar consome a vez do horário (a marca de "sem resposta" do
  ADR-0012 já foi posta), então o próximo tenta de novo só no horário seguinte.
