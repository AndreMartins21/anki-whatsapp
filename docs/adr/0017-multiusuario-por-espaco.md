# ADR-0017: Multiusuário por espaço

- **Status:** Aceito
- **Data:** 2026-09-24

## Contexto

O bot nasceu para um usuário só: `profile/me`, `session/current` e `entries/` na raiz do Firestore,
um `ALLOWED_NUMBER`, uma `asyncio.Lock` global (ADR-0006) e um agendador que lia um único perfil
(ADR-0012). O piloto num cursinho de inglês precisa de vários alunos, cada um com as próprias
palavras, sessão, perfil e lembretes, e depois de grupos (ADR-0018). O texto voltado ao usuário e o
comportamento do privado não podem mudar.

## Decisão

A unidade central é o **espaço**: o dono de um caderno de palavras. Um chat privado é um espaço
(`NUMERO@c.us`); um grupo será outro (`...@g.us`, ADR-0018).

- **Firestore:** `espacos/{espaco_id}/profile/me`, `.../session/current`, `.../entries/{slug}` (com
  `sentences`). O documento `espacos/{espaco_id}` guarda `{tipo, criado_em}` e o espelho
  `proximo_tick`. `processed/` e `lids/` continuam globais (são do webhook, não de um aluno).
- **Interface:** o `Repository` continua sendo o caderno de UM espaço, com os mesmos métodos de
  antes, então os fluxos não mudam uma linha. Um `Banco` novo (a raiz) entrega o caderno em
  `do_espaco(espaco_id)` e guarda a deduplicação, o cache de LIDs e a consulta dos lembretes.
- **Router:** monta o `Deps` de cada mensagem com o caderno do chat; há uma `Conversa` por chat (o
  limite de "3 mensagens seguidas" é por espaço) e uma `asyncio.Lock` por chat. Chats diferentes
  andam em paralelo; o mesmo chat, uma mensagem por vez.
- **Agendador:** uma consulta por tick (`listar_espacos_com_lembrete`) devolve só os espaços cujo
  `proximo_tick` já chegou. Isso usa um campo só, sem índice composto, e custa leituras
  proporcionais aos lembretes vencidos, não ao número de alunos. As três camadas de segurança do
  ADR-0012 valem por espaço, e a falha de um espaço não impede os outros.
- **Allowlist:** `ALLOWED_NUMBERS` (lista separada por vírgula); `ALLOWED_NUMBER` continua aceito e
  entra primeiro na lista. `OWNER_NUMBER` é o dono, padrão o primeiro da lista (então o
  `ALLOWED_NUMBER` legado). `ALLOWED_GROUPS` lista os grupos autorizados.
- **Aviso de erro:** vai só ao chat de quem já foi autorizado, nunca a outro aluno.
- **Migração:** `python -m scripts.migrar_multiusuario` copia a raiz antiga para o espaço do dono.
  Dry run por padrão; idempotente (entrada existente só é sobrescrita se a origem for mais nova,
  frases nunca duplicam); `--limpar-origem` é um segundo comando e recusa rodar com a cópia
  incompleta. Roda na máquina local com as credenciais padrão, não na VM. O espaço do dono é o
  `chat_id` real guardado no perfil antigo, porque a conta pode estar sem o nono dígito.

## Alternativas consideradas

- **Coleções globais com um campo `dono`** — filtros compostos, índice extra e, sobretudo, o risco de
  uma consulta esquecer o filtro e vazar dado de um aluno para outro. Com o espaço na própria
  raiz do caminho, o isolamento é estrutural.
- **Um banco por usuário** — desproporcional para 2 a 5 alunos por turma e um piloto de um mês.
- **`espaco_id` como parâmetro de cada método do `Repository`** — mexeria em todos os fluxos e em
  todos os testes; `do_espaco` deixa a mudança na borda (`Router`, `Agendador`, `main`).
- **Varrer todos os espaços a cada tick** — N leituras por minuto (com 20 espaços, quase 30 mil por
  dia, mais da metade da cota grátis). O espelho `proximo_tick` evita isso.

## Consequências

- Nenhum dado de um aluno é alcançável por outro caminho que não `do_espaco` com o id dele.
- O caderno do dono só fica visível para o bot novo depois de rodar a migração; a ordem em produção
  (dry run, executar, merge, executar de novo, smoke test, limpar) está no relatório do marco.
- Quem já tinha lembretes ligados os mantém na migração, mas se o dono mandar mensagem entre a cópia
  e o deploy, o perfil que o bot novo criou vence (o perfil só é copiado se o destino não tem um).
- `proximo_tick` é um espelho: quem grava o perfil (`salvar_perfil`) o mantém, e nenhum outro
  código deve escrever no documento do espaço.
