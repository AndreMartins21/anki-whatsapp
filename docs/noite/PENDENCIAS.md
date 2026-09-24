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
