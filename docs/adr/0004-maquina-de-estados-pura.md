# ADR-0004: Máquina de estados como função pura que devolve uma ação

- **Status:** Aceito
- **Data:** 2026-09-20
- **Fonte:** `spec/spec-inicial.md` seção 5.1

## Contexto

A conversa é uma máquina de estados com muitos atalhos (frase direta no lugar de número, palavra nova
no meio do fluxo, lista de números nas expansões). A spec exige testes de **todas** as transições. As
transições, porém, dependem de chamadas lentas e pagas a um LLM (explicar, avaliar, gerar exemplos).

## Decisão

`app/domain/state.py` contém só a decisão: `transicionar(sessao, texto, contexto)` devolve uma
`Transicao` (próximo estado + `Acao` a executar + argumento). Não chama LLM, repositório nem canal.
Os fluxos (`app/flows/`, M4) executam a ação e persistem a sessão. Onde o próximo estado depende do resultado
da ação (ex.: explicar → `AWAIT_SENSE` ou `AWAIT_CHOICE`), o estado é decidido por uma função pura
separada, também testada.

## Alternativas consideradas

- **Máquina de estados dentro dos fluxos, chamando o LLM em cada transição** — testar todas as transições
  exigiria fakes de LLM e repositório em cada caso; mistura decisão com efeito colateral.
- **Biblioteca de máquina de estados (ex.: `transitions`)** — dependência nova para ~7 estados, e o
  vocabulário da spec (atalhos por texto livre) não cabe bem no modelo evento→transição declarativo.

## Consequências

- Fácil: a tabela de transições da spec vira uma tabela de testes parametrizados, sem rede nem fakes;
  trocar o LLM ou o canal não toca a decisão.
- Difícil: há dois passos (decidir, depois executar) e o contexto que a decisão precisa (palavra-alvo,
  nº de sentidos, modo) tem que ser montado pelo chamador. A detecção de "contém a palavra-alvo" é
  heurística (flexões regulares); formas irregulares (`went`/`go`) não são reconhecidas aqui — a
  avaliação do LLM (`usa_palavra_alvo`) é quem decide de fato.
- Revisitar se: o número de estados/atalhos crescer a ponto de a tabela ficar ilegível.
