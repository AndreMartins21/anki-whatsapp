# ADR-0033: Revisão diária no grupo, sem marcar ninguém

- **Status:** Aceito
- **Data:** 2026-10-01

## Contexto

A revisão do grupo (ADR-0020) marcava um aluno por card, em rodízio, e só a resposta dele valia.
Na prática isso trava a conversa: quem não foi marcado fica de fora, e o lembrete "N vezes por dia"
(ADR-0012) não combina com uma turma que tem aula semanal. O usuário quer **uma revisão por dia**,
leve, em que qualquer aluno participe e receba feedback de verdade, e um horário que o responsável
pela turma escolha.

## Decisão

1. **Uma revisão diária por grupo**, às 19h (fuso da turma, `America/Sao_Paulo`), de segunda a sexta
   por padrão. O `Profile` do grupo ganha `diaria_ligada`, `diaria_hora`, `diaria_minuto`,
   `diaria_fim_de_semana` e `proxima_diaria`; o grupo deixa de usar `lembretes_por_dia`/janela.
2. **Ninguém é marcado.** Qualquer participante responde (`!texto`) e recebe feedback da IA. A
   **primeira resposta aceitável** (`qualidade != de_novo`) vale a nota SM-2 e avança para a próxima
   palavra; resposta errada recebe feedback e a palavra segue aberta para outro tentar.
3. **`skip` pula a palavra** (sem mexer na nota; ela continua vencida) e **`skipall` encerra** a
   revisão. Com ou sem prefixo: `!skip`, `/skip`, `/skip-all`, `/skipall`, `/1`, `/2`, `/3` valem no
   grupo (única exceção à regra "com barra a mensagem nem é lida" do ADR-0019).
4. **Quem configura:** `!daily` (ver: qualquer membro; mudar: **admins do bot** e o dono — os de
   `/admin add`). Aceita horário (`19h`, `19:30`), `on`/`off`, `weekends on|off` e `size N|auto`.
   `!reminder` vira apelido que só aponta para `!daily`; `!review` começa uma diária na hora.
5. **Fecha sozinha após 3 horas sem mensagem** do grupo (`marcacao_expira_em` espelhado em
   `espacos/{grupo}.timeout_em`, uma consulta por tick, como já era). Toda mensagem adia o prazo.
6. **Pausa contra bloqueio (ADR-0012):** depois de 3 revisões agendadas seguidas sem nenhuma
   mensagem do grupo, o agendamento pausa; a próxima mensagem de qualquer membro zera o contador. O
   privado não muda.
7. **Agenda:** `domain/agenda_grupo.py` (puro). O agendador espelha em `proximo_tick` a
   `proxima_diaria` (`proximo_tick(perfil, grupo=True)`), então segue sendo uma consulta por tick.

## Alternativas consideradas

- **Manter a marcação na diária.** Descartada: é o oposto do pedido; a marcação fica para o desafio
  semanal (ADR-0034).
- **Só `skip` avança, como no WhatsApp "aberto".** Descartada: a nota SM-2 ficaria sem dono.
- **Qualquer resposta avança (como no privado).** Descartada: uma resposta errada tiraria a palavra
  da vez sem ninguém acertar.
- **Configurar por qualquer professor.** Descartada por ora; o usuário escolheu admins do bot.

## Consequências

- **Substitui o ADR-0020** (revisão com menção em rodízio, repasse após 3h). O rodízio e a lista de
  participantes voltam no ADR-0034 (desafio semanal). Complementa o ADR-0012 (pausa no grupo) e o
  ADR-0019 (as barras acima).
- No deploy, **todo grupo ativo** passa a receber a diária às 19h nos dias úteis, inclusive os que
  estavam com `!reminder off`. Perfis antigos carregam sem migração (campos novos têm padrão).
- A nota de um card agora é a de quem acertou primeiro, não a de uma pessoa sorteada.
- Respostas continuam em `respostas/` com `marcado=false`.
