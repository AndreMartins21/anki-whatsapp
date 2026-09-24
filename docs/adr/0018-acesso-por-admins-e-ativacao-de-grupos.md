# ADR-0018: Acesso por admins e ativação de grupos

- **Status:** Aceito
- **Data:** 2026-09-24

## Contexto

Com o multiusuário (ADR-0017) e antes de o bot entrar em grupos, aparecem duas portas abertas.

1. **Grupos.** Qualquer pessoa que salve o número do bot pode adicioná-lo a vários grupos e ter um
   assistente pessoal de graça. A intenção é que só os **administradores do cursinho** possam
   ativá-lo numa turma.
2. **Privado.** Um número fora da lista era ignorado sem uma palavra. Quem escreve merece saber por
   quê, mas **a IA nunca pode ser chamada** para ele: custa dinheiro e é o caminho para o abuso.

O WAHA não ajuda a saber quem adicionou o bot: o evento `group.v2.join` só traz o grupo (`id`,
`subject`) e a lista de participantes. Não há um "adicionado por".

O produto, por enquanto, é o número do dono no privado e as turmas em grupos. Um plano mensal pago
fica para depois.

## Decisão

- **Papéis.** O **dono** (`OWNER_NUMBER`, padrão o `ALLOWED_NUMBER`) é sempre admin e o único que
  gerencia admins. **Admins** ficam em `admins/{numero}` no Firestore e o dono os gerencia por
  comando no privado (`/admin add|remove`), sem deploy. Alunos no privado seguem em `ALLOWED_NUMBERS`.
- **Ativação em vez de autorização na entrada.** Como não dá para saber quem adicionou o bot, um grupo
  só vale depois de um admin escrever `!activate` nele. Grupo ativo é o de `ALLOWED_GROUPS` (fixo,
  compat do M14) ou o ativado por admin (`espacos/{grupo}.ativo`), até `MAX_GROUPS` (padrão 10), que
  põe um teto de custo mesmo se um número de admin for comprometido.
- **Grupo não ativado: silêncio e saída em 24 h.** O evento `group.v2.join` (e qualquer mensagem de
  um grupo desconhecido) o registra em `grupos_pendentes/`. Nada é lido, gravado ou respondido, salvo
  o `!activate` de um admin. O `Agendador` sai (`POST /groups/{id}/leave`) sem mandar mensagem e apaga
  o registro; se a saída falha, tenta de novo a cada tick até 72 h e desiste (o bot pode já ter sido
  removido).
- **`!activate` de quem não é admin é silêncio total**: o bot não revela que existe nem que entende o
  comando.
- **Número sem plano no privado:** só o aviso "você não tem um plano" (inglês, com a linha 🇧🇷 em
  português, ADR-0010), no máximo uma vez por semana por número, e depois silêncio. A marca vive em
  `processed/aviso_{sha256(numero)}`, reaproveitando a TTL de 7 dias e sem guardar o telefone em
  claro. Acontece antes de qualquer chamada ao `Router`, sem `sendSeen`.
- Dono e admins veem `/groups` (ativos, pendentes e o prazo) e `/groups off N`; nada disso aparece no
  `/help`.

## Alternativas consideradas

- **Lista fixa `ADMIN_NUMBERS` em variável de ambiente** — simples, mas trocar um admin exige deploy
  (merge na `main`, ADR-0013). O cursinho troca de pessoal.
- **Só o dono ativa grupos** — o mais seguro, mas todo grupo novo passa por uma pessoa só.
- **Sair na hora, avisando** — deixa claro, mas é uma mensagem não pedida e pode sair de um grupo
  legítimo antes de o admin digitar `!activate`.
- **Ficar em silêncio para sempre** — não custa nada, mas acumula grupos e a lista de pendentes só
  cresce.
- **Confiar em "Privacidade → Grupos → Meus contatos" no WhatsApp** — ajuda (recomendado no README),
  mas é uma configuração do celular, não uma garantia do software.

## Consequências

- Só admins põem o bot para trabalhar em grupo, e o custo dos grupos tem teto (`MAX_GROUPS`).
- **Responder a estranhos é um risco de reputação:** cada número novo que escrever recebe uma
  mensagem, e um bot que responde a desconhecidos é um sinal para o WhatsApp. O limite de uma por
  semana por número reduz isso, mas não há teto global. Se o bot virar alvo de spam, o caminho é
  ignorar em silêncio (uma linha) ou limitar as respostas por hora.
- O campo do participante em mensagens de grupo (`@c.us` ou `@lid`) no GOWS só se confirma no
  WhatsApp real. Se vier de um jeito que o cache `lids/` não resolve, nenhum admin consegue ativar
  um grupo, e a saída é `ALLOWED_GROUPS` (que já existe).
- Desativar um grupo mantém o caderno da turma. Quando os lembretes de grupo existirem (M17), o
  agendador tem que conferir se o grupo ainda está ativo.
- Os planos pagos (autocadastro de alunos, cobrança) estão fora deste ADR.
