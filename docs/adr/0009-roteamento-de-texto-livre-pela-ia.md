# ADR-0009: Roteamento de texto livre por uma chamada de IA, máquina de estados reduzida a dois estados

- **Status:** Aceito
- **Data:** 2026-09-22

## Contexto

A máquina de estados original (ADR-0004, spec §5.1 antes do M9) tinha 9 estados e 6 menus
diferentes, cada um com heurísticas próprias em `app/domain/choices.py` para decidir se um texto
livre era uma frase de prática (`contem_palavra_alvo`), uma palavra nova (`≤4 palavras sem o
alvo`) ou "não entendi" (`REENVIAR_MENU`). Qualquer coisa fora desse script — um pedido de
pronúncia, "e outro sentido dessa palavra?", uma pergunta de gramática — caía sempre em "Não
entendi 😅". O M9 pede que o bot entenda linguagem natural: frase para corrigir, pedido de ajuda,
palavra nova ou fora do escopo, tudo dentro da mesma conversa.

## Decisão

A máquina de estados (`app/domain/state.py`) encolhe para `IDLE` e `AWAIT_ACTION`, com um único
menu de 3 opções (`app/domain/choices.py:MENU_ACOES`). Texto livre que não é uma opção do menu
vira `Acao.ROTEAR`; o `Router` (não a máquina, que continua pura — ADR-0004) chama
`Tutor.route(palavra, sentido, texto, nivel)`, **uma única chamada de IA** que classifica a
intenção (`frase | exemplos | sinonimos | salvar | nova_palavra | pedido | fora_do_escopo`, schema
`Roteamento`) e **já devolve o conteúdo da resposta** no mesmo payload — para `frase`, os mesmos
campos de `Evaluation`; para `pedido`/`fora_do_escopo`, o texto já pronto em `resposta`. O fluxo
`app/flows/freeform.py` despacha por `match` para `capture`/`practice`/`synonyms` conforme a
intenção. `Roteamento` é achatado de propósito (só primitivos, enums e `list[str]`, sem objeto
aninhado opcional) para caber bem no `response_schema` do Gemini, no mesmo espírito de
`Explanation` com `ok=False` (ADR-0005): campos não usados pela intenção ficam com valor padrão.

## Alternativas consideradas

- **Classificar e depois responder (2 chamadas)** — uma chamada barata só para a intenção, depois
  a chamada da tarefa específica (`evaluate`/`examples`/resposta livre). Mais fácil de testar
  isoladamente, mas dobra latência e custo em toda mensagem livre — que é o caminho mais comum
  numa conversa natural. Fica registrado como plano B se o schema achatado do `Roteamento` se
  mostrar frágil no `response_schema` do Gemini.
- **Manter as heurísticas determinísticas de `choices.py`** (contagem de palavras, presença da
  palavra-alvo) e só adicionar um caso `else` para "pedido livre" — não resolve o problema: o pedido
  de ajuda continua sem resposta, e a heurística de "≤4 palavras = palavra nova" já era frágil
  (frases curtas sem o alvo, como "up we gave", davam falso positivo).

## Consequências

- Fácil: a spec (§5.1) fica muito mais curta; um menu só para testar e documentar; texto livre
  responde a praticamente qualquer coisa relacionada a aprender inglês.
- Difícil: a decisão de "é frase ou é palavra nova?" que antes era determinística e testável sem
  IA agora depende do modelo acertar a intenção — mitigado por `evals/roteamento.yaml`
  (`python -m evals.run --tarefa roteamento`), que mede a taxa de acerto por intenção contra a API
  real antes de trocar de modelo ou de prompt.
- Cada mensagem livre no meio de uma palavra é 1 chamada de IA (antes podiam ser 0, quando a
  heurística resolvia sozinha) — aceitável no volume de um único usuário; monitorar se isso pesar
  no custo do Vertex AI.
- Revisitar se: o eval de roteamento mostrar uma intenção sistematicamente mal classificada (nesse
  caso, considerar a alternativa de 2 chamadas só para essa distinção) ou se o `response_schema`
  achatado ainda assim causar problema real com o Gemini.
