# Pendências e decisões tomadas sem perguntar

Formato: o que estava ambíguo, o que foi escolhido, por quê.

## M14 — Multiusuário

- **Dono padrão.** O plano diz "padrão = primeiro número de `ALLOWED_NUMBERS`". Escolhi: o
  `ALLOWED_NUMBER` antigo vem primeiro na lista (então é o dono), e só sem ele vale o primeiro de
  `ALLOWED_NUMBERS`. Motivo: o `ALLOWED_NUMBER` atual é o do usuário; se ele adicionar alunos em
  `ALLOWED_NUMBERS` sem tirar o antigo, o dono não pode virar um aluno, porque é o dono que recebe
  as palavras na migração. `OWNER_NUMBER` explícito sempre vence.
