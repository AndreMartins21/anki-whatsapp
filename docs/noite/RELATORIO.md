# Relatório — turmas (M14 a M17)

Branch `feat/turmas`, **sem push e sem PR** (a `main` protegida faz deploy no merge). `make check`
verde (701 testes) e `make test-emulador` verde (110 testes de contrato e migração no Firestore).

## 1. Marcos

| Marco | Commit | O que entrega |
|---|---|---|
| M14 | `7e1feca` | Multiusuário por espaço (`espacos/{chat}/...`), `Banco` + `Repository`, `ALLOWED_NUMBERS`/`ALLOWED_GROUPS`/`OWNER_NUMBER`, trava e `Conversa` por espaço, agendador por espaço, `scripts.migrar_multiusuario` |
| M15 | `875bab3` | Controle de acesso: número sem plano só recebe um aviso (sem IA), admins no Firestore (`/admin`), grupo só por `!activate` de admin (`/groups`, `MAX_GROUPS`), grupo não ativado sai em 24 h |
| M16 | `25102c3` | Bot em grupo: só lê o prefixo `!`, conjunto fechado de comandos, papéis, `sim --grupo` |
| M17 | `2f3671b` | Revisão em grupo: um aluno marcado por card, rodízio, timeout com repasse |

**Não feito:** M18 (`/privacy`, `/forget`, métricas do piloto).

ADRs 0017 a 0020, spec e README atualizados junto de cada marco. Decisões tomadas sem perguntar e riscos:
`docs/noite/PENDENCIAS.md`.

## 2. Testes antigos que mudaram

Só assinatura (`Router.processar(texto, chat_id)`, `Agendador(banco=...)`, `exportar(repo)`), mais dois
comportamentos que o pedido mudou de propósito: número não autorizado agora recebe o aviso (antes era
ignorado) e `test_destino_pode_mudar_por_mensagem` virou "a resposta vai ao chat de quem escreveu".
Nenhum teste do privado mudou de texto ou de lógica.

## 3. WAHA: o que foi confirmado na doc e o que é suposição

Confirmado: `sendText` com `mentions: ["NUM@c.us"]` e `@NUM` no texto (GOWS incluído); participantes em
`GET /api/{session}/groups/{id}/participants/v2` (só `{id, role}`); sair do grupo em
`POST /api/{session}/groups/{id}/leave`; evento `group.v2.join` (traz `group.id`/`subject` e **não** diz
quem adicionou); o remetente em grupo em `payload.participant`.

Suposição (não documentado): nome de quem escreveu (`_data.pushName`/`Info.PushName`), `mentionedIds`
nas mensagens recebidas, e se o `participant` vem como `@c.us` ou `@lid` no GOWS.

## 4. Só dá para validar no WhatsApp real

1. **Privado (você):** palavra, `/list` e `!list`; tudo como antes.
2. **Estranho:** de outro número, "oi" → o aviso (com a linha em português); a 2ª mensagem não responde nada.
3. **Grupo novo:** crie um grupo com o bot (no celular do bot: Privacidade → Grupos → "Meus contatos").
   Nada deve responder. No privado, `/groups` mostra o grupo como pendente, com as horas até o bot sair.
4. **`!activate`** no grupo (você é o dono, logo admin) → "I'm active…". Um amigo não-admin manda
   `!activate` → silêncio.
5. **Ciclo:** `!add stall | the talks stalled`, `!1`, `!<uma frase>`, `!3`; conversa sem `!` é ignorada.
6. **Remetente:** se um amigo aparece como `@lid`, o comando dele funciona (o cache `lids/` resolve)?
7. **Nome:** `!group` mostra os nomes ("Student N" se o WhatsApp não os der no payload).
8. **Papéis:** `!teacher 5531...` (número escrito) e com `@menção`, para ver se o payload traz `mentionedIds`.
9. **Revisão:** `!review` → a menção **notifica** a pessoa (LID); a resposta dela avança; a de outro dá
   feedback sem avançar; `!0` fecha.
10. **Timeout:** ponha `TIMEOUT_MARCACAO_HORAS=0.05` (3 min) para ver o repasse e o fechamento sem esperar.
11. **Saída em 24 h:** um grupo pendente por mais de 24 h faz o bot sair sem mensagem.

## 4b. Como testar sem produção

`make sim ARGS=--grupo` (linhas `ana: !add stall`, `ana: !review`, `~timeout`).

## 5. Passos para produção, na ordem (nada foi executado)

Nada abaixo é obrigatório para **testar**: as variáveis novas são opcionais (o `ALLOWED_NUMBER` atual
continua sendo o dono, e seus dados antigos ficam intactos na raiz do Firestore).

1. (Opcional) GitHub → Secrets: `ALLOWED_NUMBERS` (alunos), `OWNER_NUMBER`. Variables: `MAX_GROUPS`,
   `CONTACT_EMAIL`, `GROUP_PREFIX`, `LIMITE_POR_SESSAO_GRUPO`, `TIMEOUT_MARCACAO_HORAS`.
2. Migração em dry run, na sua máquina, com `gcloud auth application-default login`:
   `python -m scripts.migrar_multiusuario --projeto ID`.
3. Migração de verdade: a mesma linha com `--executar`.
4. Push da branch, PR (rascunho, depois pronto) e **merge** (o merge faz o deploy; o compose passa a
   assinar `group.v2.join`).
5. Migração de novo (`--executar`): traz o que o bot antigo gravou entre a cópia e o deploy.
6. Smoke test no WhatsApp (a lista da seção 4).
7. Só então `--limpar-origem`.
