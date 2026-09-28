# ADR-0030: Pedido de sentido (`palavra | sentido`) e palavra de qualquer nível

- **Status:** Aceito
- **Data:** 2026-09-28

## Contexto

Dois problemas de uso apareceram nos grupos:

1. **Recusa por nível.** Num espaço A2-B1, palavras avançadas e gírias (`no cap`, `gaslight`)
   voltavam como "That doesn't look like an English word". Não existe filtro no código: o
   `prompt_explain` só mandava `ok=false` para "não é inglês", mas o `_sistema` injetava o nível do
   aluno sem dizer que ele não restringe a palavra-alvo, e o Gemini passou a recusar por conta própria.
2. **Palavras com vários sentidos.** `Explanation.sentidos` já traz de 1 a 4, mas o card mostrava só o
   escolhido. O aluno não sabia que havia outros nem como pedi-los. E o único jeito de pedir um
   sentido (`stall | to delay on purpose`, o formato de contexto do ADR-0023) falhava de duas formas:
   em `AWAIT_ACTION` o texto ia para `Tutor.route` (ADR-0009), que o tratava como `pedido` e só
   respondia em texto; em `IDLE`, `gravar_entrada` via `frase_contexto=None` (não é uma frase) e
   dizia "📌 You already have *stall*", com o sentido antigo.

## Decisão

1. **Qualquer palavra entra.** O `_sistema` diz que o nível calibra só o vocabulário de apoio, e o
   `prompt_explain` manda aceitar palavra rara, técnica, gíria, informal, abreviação e palavrão,
   **nunca** `ok=false` por nível, raridade ou registro; o registro vira aviso na `nota`.
2. **O card lista os outros sentidos** (`↔️ tradução — definição`, o mesmo formato do `/info`) e ensina
   a pedir um: `Want another meaning? Send *stall | to delay on purpose*` (no grupo, com `!add`).
3. **`palavra | sentido` é uma ação da máquina de estados**, `Acao.EXPLICAR_COM_CONTEXTO`, tratada
   em `AWAIT_ACTION` sem a IA de roteamento: texto com `|` e conteúdo dos dois lados. Com o termo da
   palavra aberta é pedido de sentido; com outro termo é palavra nova. O `prompt_explain` aceita
   depois do `|` uma frase **ou** o sentido desejado.
4. **Troca do card recém-criado.** Se a entrada foi criada por esta captura e o aluno ainda não
   escreveu frase nela, o novo sentido a substitui; a IA responde antes e só então a antiga é
   apagada, então uma falha não perde nada. Com frase escrita, o novo sentido vira outro card (`--s2`).
5. **Um pedido de sentido nunca é "já existe".** `gravar_entrada(pediu_sentido=True)` desliga a regra
   "palavra sozinha já salva" do ADR-0023, e o `resolver_slug` decide entre sentido igual e `--sN`.

## Alternativas consideradas

- **Deixar o pedido de sentido no roteamento de IA (`pedido`).** Descartada: a resposta é só texto e
  não cria card; teria de ensinar a IA de roteamento a devolver uma nova intenção, com uma segunda
  chamada.
- **Sempre criar um card extra ao pedir outro sentido.** Descartada por decisão do usuário: quem pede
  outro sentido logo depois do card quase sempre queria aquele no lugar do primeiro; sobrariam cards
  errados na lista. O card extra fica só quando já há uma frase do aluno (trabalho a preservar).
- **Filtrar o nível no código (lista de palavras permitidas).** Descartada: não há filtro a remover;
  o problema é comportamento do modelo e se conserta no prompt.
- **Mostrar todos os sentidos como menu numerado.** Descartada: o menu é único (ADR-0009) e o
  formato `palavra | sentido` funciona igual no privado e no grupo.

## Consequências

- Complementa os ADR-0009 (um formato de texto sai do roteamento por IA) e ADR-0023 (regra de "já
  existe" com sentido pedido); ambos seguem Aceitos.
- O card ganha 2+ linhas quando a palavra tem outros sentidos; o texto da dica depende da definição
  do primeiro deles.
- A qualidade do "sentido pedido" depende do modelo: `make evals`/testes reais não cobrem isso; o
  contrato testado é o do prompt e do fluxo, com `FakeTutor`.
- Um aluno que digitar `palavra | outra coisa` com o termo da palavra aberta sempre recebe um novo
  card (troca ou `--sN`), nunca o roteamento livre.
