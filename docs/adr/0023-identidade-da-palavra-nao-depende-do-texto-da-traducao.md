# ADR-0023: A identidade da palavra não depende do texto da tradução que a IA devolve

- **Status:** Aceito
- **Data:** 2026-09-25

## Contexto

O ADR-0021 fez o bot avisar quando a palavra já está na lista. Em produção, no mesmo dia, o aviso
não apareceu: o aluno reenviou `grader` e recebeu um card novo, e o Firestore ganhou `grader--s2`.

A causa: `resolver_slug` decidia "é o mesmo sentido" comparando o **texto** da tradução com `==`,
e a IA reescreve a tradução a cada chamada. Sem frase de contexto, o prompt pede "o sentido mais
comum", mas a redação muda ("avaliador" → "avaliador ou sistema de correção"). Texto diferente
virava "outro sentido" e abria `--s2`. O `grader--s2` foi criado às 18:23 UTC, depois do deploy do
ADR-0021; a lista já tinha `grader`.

## Decisão

- **Palavra sem frase de contexto** (`frase_contexto` nulo): se a palavra já tem alguma entrada
  (`slug` ou `slug--sN`), é essa entrada, em qualquer sentido salvo (a de slug-base primeiro).
  Sem frase, o aluno não escolheu um sentido; o "mais comum" é sorteio da IA.
- **Palavra com frase de contexto:** segue o critério por sentido, mas duas traduções contam como
  o mesmo sentido se têm **alguma opção em comum** (`mesma_traducao`: separa por `,` `;` `/` e
  `ou`, ignora acento, maiúscula e o que está entre parênteses). Só traduções sem nada em comum
  abrem `--sN`.

## Alternativas consideradas

- **Só a comparação flexível de tradução** — não cobre a palavra sozinha cujo sentido "mais comum"
  muda de fato entre chamadas ("parar de funcionar" vs "enrolar").
- **Mandar à IA os sentidos já salvos e pedir o `id` do que coincide** — mais preciso, mas gasta
  tokens em toda captura e cria um contrato novo no prompt; revisitar se a regra acima errar.
- **Comparar a definição em inglês ou por embedding** — custo e complexidade sem evidência de
  necessidade.

## Consequências

- Reenviar uma palavra da lista mostra o aviso (ADR-0021) de forma estável, e a lista para de ganhar
  duplicatas por variação de redação.
- Quem quer registrar um segundo sentido de propósito precisa mandar uma frase (`stall | I bought
  it at a stall`), com tradução sem opção em comum.
- Falso positivo possível: dois sentidos distintos com uma tradução em comum são fundidos. Se isso
  aparecer, é o gatilho para a alternativa da IA escolher o `id`.
- Duplicatas antigas (`grader--s2`) não são migradas; o aluno apaga com `/delete`.
