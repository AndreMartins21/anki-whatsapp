# ADR-0025: Lembretes ligados por padrão e tamanho da fila de revisão configurável

- **Status:** Aceito
- **Data:** 2026-09-27

## Contexto

Desde o M10 os lembretes (spec §5.7) vêm **desligados por padrão** — a spec original justificava
isso como "não mandar mensagem sem o aluno pedir". Na prática, isso empurra a descoberta da
revisão espaçada para uma dica de uma linha depois da primeira palavra salva, e o aluno que não
lê com atenção nunca liga os lembretes sozinho — o recurso mais valioso do bot (o que o traz de
volta) fica escondido atrás de um passo extra que a maioria não dá.

A fila de uma sessão de revisão também era um número fixo (`LIMITE_POR_SESSAO = 20`), igual para
todo mundo, independente de quantas palavras a pessoa realmente tem ou de quanto tempo ela quer
gastar numa sessão.

## Decisão

**Lembretes ligados por padrão**, 1x por dia às 12h, para todo **perfil novo**. Continuam
totalmente configuráveis (`/reminders N INICIOh-FIMh`) e podem ser desligados
(`/reminders off`) a qualquer momento — a decisão nova é só o ponto de partida. **Só vale para
perfil novo**: quem já tinha conta antes deste marco não muda sozinho, porque isso mandaria
mensagem sem ter sido pedido para quem nunca configurou nada — exatamente o problema que a decisão
original tentava evitar.

**Tamanho da fila de revisão dinâmico**: `MIN(palavras do aluno, 7)` por padrão, no lugar do `20`
fixo. `/reviewsize N` (1 a 20) fixa um valor; `/reviewsize auto` volta ao dinâmico; o último
parâmetro de `/reminders`, **quando dado**, faz a mesma coisa, para configurar tudo de uma vez sem
precisar de dois comandos — **omitido, `/reminders` não mexe no tamanho da fila**, para não resetar
sem querer um `/reviewsize` configurado antes só porque a pessoa quis mudar o horário do lembrete.
Um valor fixo vale também no grupo, sobrepondo o `LIMITE_POR_SESSAO_GRUPO` padrão.

A dica de uma linha depois da primeira palavra salva (`avisou_lembretes`) só aparece agora quando
os lembretes estão de fato desligados (quem desligou antes de salvar a primeira palavra) — com o
padrão ligado, a dica deixou de fazer sentido para a maioria.

## Alternativas consideradas

- **Manter desligado por padrão, só melhorar a dica** — mais simples e sem reverter a decisão
  antiga, mas não resolve o problema real: a dica já existe desde o M10 e a maioria não liga o
  comando sozinha.
- **Ligar por padrão também para perfil existente** (migração retroativa) — mandaria a primeira
  mensagem de uma conversa para gente que nunca pediu isso, o exato risco que a spec original
  queria evitar (e o tipo de padrão que motiva bloqueio de conta no WhatsApp). Só vale para quem
  cria conta a partir de agora.
- **Tamanho da fila sempre fixo em um número menor** (ex.: 7 para todo mundo) — mais simples que o
  dinâmico, mas trata igual quem tem 3 palavras e quem tem 300; o dinâmico degrada bem para quem
  está começando (sessão do tamanho que a pessoa tem) sem abrir mão de um teto sensato para quem já
  tem muitas.
- **`/reminders` sem o último parâmetro sempre reseta o tamanho para 7** — foi a primeira versão
  implementada, descartada em revisão: qualquer `/reminders N INICIOh-FIMh` para só mudar o horário
  apagava, sem aviso, um `/reviewsize` fixado antes. Omitido passar a significar "não mexe" evita
  esse efeito colateral, ao custo de `/reminders` e `/reviewsize` poderem divergir do que a pessoa
  via da última vez que configurou os dois juntos — aceitável, porque cada comando mexe só no que
  diz que mexe.

## Consequências

- Fácil: quem nunca mexeu em nada já sai da criação da conta com uma reserva diária de prática;
  o comando `/reviewsize` reaproveita o parser e a validação que `/reminders` já tinha.
- Difícil: perfis novos e antigos agora têm comportamentos de partida diferentes para o mesmo
  campo (`lembretes_por_dia`), o que exige lembrar, ao ler o código, que o valor "padrão" do modelo
  só vale para quem nunca foi salvo antes — não existe migração, então essa divergência é
  permanente até o dia em que não sobrar mais perfil anterior ao M24.
- Revisitar se: o padrão de 1x às 12h se mostrar um horário ruim na prática (ex.: muita gente
  desligando logo de cara), ou se fizer sentido perguntar o horário preferido na primeira
  interação em vez de escolher por todo mundo.
