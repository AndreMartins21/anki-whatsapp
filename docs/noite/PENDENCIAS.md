# Pendências e decisões tomadas sem perguntar

Formato: o que estava ambíguo, o que foi escolhido, por quê.

## M14 — Multiusuário

- **Dono padrão.** O plano diz "padrão = primeiro número de `ALLOWED_NUMBERS`". Escolhi: o
  `ALLOWED_NUMBER` antigo vem primeiro na lista (então é o dono), e só sem ele vale o primeiro de
  `ALLOWED_NUMBERS`. Motivo: o `ALLOWED_NUMBER` atual é o do usuário; se ele adicionar alunos em
  `ALLOWED_NUMBERS` sem tirar o antigo, o dono não pode virar um aluno, porque é o dono que recebe
  as palavras na migração. `OWNER_NUMBER` explícito sempre vence.

## M15 — Controle de acesso

- **Texto do aviso em inglês.** O pedido foi um texto em português. O ADR-0010 manda a interface em
  inglês, com o PT-BR só na linha 🇧🇷. Escolhi os dois: o aviso em inglês e, na linha 🇧🇷, a frase em
  português que o usuário ditou. Se preferir só português, é uma linha em `messages.sem_plano`.
- **`/help` não lista `/groups` nem `/admin`,** nem para admin (o plano só pedia escondê-los de quem não
  é admin). Fica como está; é uma linha se quiser mostrar aos admins.
- **Campo do remetente em grupo no GOWS.** A doc do WAHA diz `participant` (`@c.us`); se o GOWS mandar
  `@lid`, o cache `lids/` resolve. Não dá para confirmar sem o WhatsApp real. Plano B: `ALLOWED_GROUPS`.
- **Sem teto global de avisos a estranhos** (só 1 por número por semana). Risco de reputação registrado no
  ADR-0018.
- **`!activate`/`!deactivate` usam o prefixo `!` fixo** até o M16 trazer `GROUP_PREFIX`.
- **Lembretes de grupo desativado (M17):** o agendador precisa conferir se o grupo ainda está ativo.
- **Custo:** o tick lê `grupos_pendentes` (1 leitura por minuto quando vazio, ~1440/dia) — desprezível
  frente aos 50 mil/dia da cota grátis.
- **Recusa acima do limite** avisa no grupo (`grupo_limite`) para o admin entender por que o bot não
  responde; um não admin nunca recebe nada.

## M16 — Grupo com prefixo

- **Nome e menções no payload do WAHA.** A doc não documenta o nome de quem escreveu nem os ids
  mencionados. Leio vários formatos (`_data.pushName`, `notifyName`, `_data.Info.PushName`;
  `mentionedIds`), e o que faltar vira "Student N" / número escrito no texto (`!teacher 5531...`
  sempre funciona). **Validar no WhatsApp real.** Se a menção vier como `@<LID>` digitado no texto, não
  resolvo (só o campo `mentionedIds`).
- **`!` só vale com letra ou número logo depois** (`!!!`, `! `, `!` são conversa): evita o bot
  responder a exclamações. O plano só dizia "começa com o prefixo".
- **Frase de prática que começa com nome de comando** (`!list of things...`) é lida como comando (custo
  de manter o conjunto de comandos pequeno; está no ADR-0019).
- **Sem `!level` no grupo:** o nível é o `USER_LEVEL` padrão. Dá para acrescentar depois.
- **`!add` com outra palavra aberta** salva a anterior antes (igual ao privado com palavra nova).
- **Quem nunca mandou `!`** não aparece no `!group` (o endpoint de participantes só devolve ids; o
  M17 usa a lista de participantes só para a revisão).
- **Grupo desativado** para de receber lembretes (espelho `proximo_tick` limpo + conferência do
  agendador); reativar os devolve.

## M17 — Revisão em grupo

- **Menção de quem aparece como LID no grupo.** Mando `mentions: ["NUMERO@c.us"]` com o número
  resolvido (formato da doc do WAHA). Se o participante for um LID e o WhatsApp só entender a menção
  pelo LID, a pessoa pode não ser notificada (o texto ainda mostra `@numero`). **Validar no WhatsApp
  real**; o plano B é marcar pelo LID (o cache `lids/` guarda a relação inversa se for preciso).
- **`participants/v2` no GOWS:** a doc lista o endpoint como suportado no GOWS, mas o formato do `id`
  (`@c.us` ou `@lid`) só se vê no real. LIDs sem número conhecido ficam de fora da rodada.
- **Lista vazia de participantes é tratada como falha** (usa o cadastro de `membros/`).
- **Lembrete sem aluno para marcar** consome a vez do horário (`lembrete_sem_resposta` já foi posto
  antes de chamar a revisão); o próximo tenta de novo no horário seguinte. É raro (grupo só com
  professores) e evita um laço de tentativas.
- **Quem responde durante a revisão** e não é a pessoa marcada recebe feedback, mas o `!list`, `!group`
  etc. viram respostas até a rodada fechar (só `!0`, `!stop` e `!help` escapam). Decidi assim para a
  rodada não ser interrompida por comandos soltos; se atrapalhar a discussão, é fácil afrouxar.
- **Timeout máximo de 6 h por rodada** (3 h + 3 h do repasse); o padrão vem do plano.
- **Sem métricas ainda:** `respostas/` está gravando; o script de métricas é o M18 (não feito).
