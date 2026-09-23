# ADR-0012: Agendador de lembretes no próprio processo, com destino persistido e trava de iniciativa

- **Status:** Aceito
- **Data:** 2026-09-23

## Contexto

A revisão espaçada (ADR-0011) só funciona se o bot **iniciar** a conversa no horário certo — até
aqui (M0-M9) o bot só falava depois de receber uma mensagem. Isso muda uma premissa de segurança
importante da spec §5.6 ("nunca mande mensagem para número diferente do `ALLOWED_NUMBER`", "nunca
mande mais de 3 mensagens seguidas sem resposta"): agora existe um caminho de código que manda a
**primeira** mensagem de uma conversa, o que é justamente o padrão que motiva bloqueios de conta
no WhatsApp quando feito sem cuidado.

## Decisão

Um `asyncio.Task` criado no `_lifespan` do FastAPI (`app/main.py`), rodando `Agendador.rodar()`
(`app/services/lembretes.py`) — um laço que acorda a cada 60 s e decide, em `_tick`, se é hora de
disparar. O próximo horário (`profile/me.proximo_lembrete`) fica no Firestore, não em memória:
sobrevive a um restart do container. Três camadas de segurança, todas verificadas antes de mandar
qualquer coisa:

1. **Só dispara com um `chat_id` real**, aprendido de `Router.processar` quando uma mensagem
   chega (nunca do `ALLOWED_NUMBER` do `.env` diretamente — a lição de `b141c39`, spec §8.2, é
   que o número real pode diferir no nono dígito). Sem `chat_id` conhecido, o agendador fica calado.
2. **Nunca sem fila** — se não há nada vencido, o agendador recalcula o próximo horário e não manda
   nada (silêncio em vez de "spam" de "nada para revisar").
3. **Nunca dois lembretes seguidos sem resposta** (`profile/me.lembrete_sem_resposta`): marcado ao
   disparar, limpo pelo `Router.processar` na primeira mensagem que o aluno mandar depois (mesmo
   que não seja resposta à revisão). Um lembrete atrasado (>2 h) ou sem resposta ao anterior faz o
   agendador desistir daquele horário e recalcular o seguinte, em vez de acumular.

Além disso, `Router.iniciar_revisao()` usa a **mesma `asyncio.Lock`** de `Router.processar`
(ADR-0006): a revisão nunca começa no meio de uma mensagem sendo processada, e nunca interrompe
uma conversa em andamento (`sessao.estado != IDLE` adia, não força).

## Alternativas consideradas

- **Cloud Scheduler → endpoint HTTP** — o padrão nativo do GCP para isso, mas exigiria abrir
  ingress na VM (hoje sem porta pública, ADR-0007) ou uma peça extra (Cloud Run só para receber o
  gatilho e chamar a VM via IAP), complexidade desproporcional para um lembrete de uma vez por
  algumas horas, para um usuário só.
- **Cron no host da VM** chamando um script/endpoint — funciona, mas é mais uma peça de infra fora
  do `docker-compose.yml` (ADR-0001 já limita a VM a `waha` + `bot`), com seu próprio agendamento
  de fuso e sua própria forma de falhar silenciosamente.
- **Guardar o estado do agendador só em memória** (sem persistir `proximo_lembrete`) — mais simples,
  mas um restart do container (deploy, OOM, `unless-stopped` reiniciando) perderia o horário e só
  recalcularia no primeiro tick depois de subir; como o cálculo é barato e determinístico a partir
  de `janela_inicio`/`janela_fim`/`lembretes_por_dia`, persistir é a diferença entre "o lembrete
  pode atrasar até 1 minuto" e "o lembrete pode sumir até o próximo tick puro depender de outra
  coisa acontecer" — persistir é mais previsível e quase de graça.

## Consequências

- Fácil: nenhuma peça de infra nova (nem porta, nem serviço, nem cron) — só um `asyncio.Task` a
  mais no mesmo processo que já roda o webhook; os testes (`tests/test_agendador.py`) rodam a
  decisão de um tick isolada, com relógio controlado, sem `sleep` real nem rede.
- Difícil: se o container do bot está parado (deploy, crash), nenhum lembrete sai enquanto ele
  estiver fora — aceitável (`restart: unless-stopped` já limita o tempo fora do ar) para o volume
  de um usuário só; um gatilho externo teria a mesma limitação de qualquer forma, já que o `bot` é
  quem manda a mensagem.
- O tick de 60 s é uma cota de precisão (o lembrete pode atrasar até ~1 min) — nunca reduzir esse
  intervalo sem motivo: mais ticks só custam CPU na VM `e2-micro` sem ganho perceptível para um
  lembrete de granularidade de hora.
- Revisitar se: o projeto ganhar mais de um usuário (o agendador hoje lê um único `profile/me`) ou
  se a VM ganhar uma porta pública por outro motivo, o que tornaria o Cloud Scheduler viável sem o
  custo extra de abrir ingress só para isso.
