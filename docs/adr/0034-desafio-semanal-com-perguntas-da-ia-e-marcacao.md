# ADR-0034: Desafio semanal do grupo, com perguntas da IA e marcação em rodízio

- **Status:** Aceito
- **Data:** 2026-10-01

## Contexto

A revisão diária (ADR-0033) cobre lembrar o sentido de cada palavra, sem cobrar ninguém. Falta um
momento da semana em que **cada aluno seja chamado a falar**, e em que use o vocabulário da turma em
vez de só explicá-lo. Perguntar "o que significa X?" repetido vira cansativo; uma pergunta aberta,
no nível da turma, que mistura palavras do vocabulário, exercita o uso.

## Decisão

1. **Um desafio por semana**, padrão sexta-feira às 13h (`Profile.semanal_*`, fuso da turma),
   configurável por `!weekly [dia] [hora] [size N|auto] [on|off]`; `!weekly now` o começa na hora.
   Ver: qualquer membro; mudar e `now`: admins do bot e o dono (como o `!daily`).
2. **Perguntas da IA** (`Tutor.weekly_questions`): uma chamada gera as `n` perguntas no nível da
   turma com palavras do vocabulário do grupo (`escolher_vocabulario`: as da última semana primeiro,
   completando até 15). `n` = uma por aluno elegível por padrão (teto 10); `!weekly size N` fixa.
   A complexidade vem do nível (A1-A2 curtas e concretas … C2 hipóteses e nuance).
3. **Marcação em rodízio** (a mesma de `domain/rodizio.py`, ADR-0020): cada pergunta marca um aluno,
   nunca professor nem o bot; **a mensagem sempre começa pela menção**, depois a pergunta (palavras do
   vocabulário em negrito) e o menu `/1 Explain the question`, `/2 Listen to the question`,
   `/3 Skip this question`.
4. **Quem responde:** qualquer um pode tentar e recebe feedback (`Tutor.weekly_answer`), mas a
   pergunta **só avança quando a pessoa marcada responde** ou alguém pula (`3`, `skip`).
   `skipall`/`0`/`stop` encerra. Não mexe no SM-2: é conversa, não revisão de cartão. `respostas/`
   registra `{entry = 1ª palavra, autor_id, marcado}`.
5. **Menu:** `1` explica a pergunta — turma A1-A2/A2-B1: **português primeiro e depois inglês**;
   de B1-B2 em diante, só inglês (ADR-0032). `2` lê a pergunta com o Cloud TTS (cache por hash já
   existente); sem áudio configurado, avisa. `3` pula.
6. **Estado novo `WEEKLY_QUIZ`** na máquina de estados pura (transições testáveis); a sessão guarda
   as perguntas e o placar. A rodada **fecha sozinha após 3 horas sem mensagem** (mesmo mecanismo do
   ADR-0033) e respeita a pausa de 3 revisões sem resposta (ADR-0012).
7. **O semanal tem precedência** sobre a diária se vencem no mesmo tick, e usa o mesmo espelho
   `proximo_tick` (o menor dos dois horários), então segue sendo uma consulta por tick.

## Alternativas consideradas

- **Gerar uma pergunta por turno.** Descartada: latência a cada resposta e risco de repetir
  palavras; gerar tudo de uma vez é uma chamada só e deixa `!1` e `!2` sem IA.
- **Repasse automático se o marcado não responde.** Descartada: o usuário quer que só o marcado (ou
  um skip) avance; o fechamento após 3h evita travar o grupo.
- **Dar nota SM-2 à resposta.** Descartada: a pergunta mistura palavras, não há um cartão só.
- **Português sempre na explicação.** Descartada: de B1-B2 em diante o objetivo é pensar em inglês.

## Consequências

- **Exceção explícita à regra "todo texto em inglês" (ADR-0010):** a explicação da pergunta em turma
  iniciante vem em português antes do inglês (a regra 4 do `CLAUDE.md` cita a exceção).
- No deploy, todo grupo ativo passa a receber o desafio às sextas 13h (se houver palavras e ao menos
  um aluno); o professor ajusta ou desliga com `!weekly`.
- Cada desafio custa uma chamada de geração mais uma de avaliação por resposta (centavos).
- Menção em LID segue sem confirmação no WhatsApp real (ver ADR-0020).
