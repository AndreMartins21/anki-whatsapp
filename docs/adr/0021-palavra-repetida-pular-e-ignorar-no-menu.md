# ADR-0021: Palavra repetida avisa e mostra o que já existe; `0`/`skip` saem da palavra e a opção 4 a descarta

- **Status:** Aceito
- **Data:** 2026-09-25

## Contexto

Duas fricções no uso diário (ADR-0009 deixou o menu único em `AWAIT_ACTION`):

- Mandar uma palavra que já estava na lista devolvia o card completo, como se fosse nova, sem
  avisar. O aluno não sabia que estava repetindo, e o exemplo mostrado podia ser diferente do
  que já estava salvo.
- Para trocar de palavra em `AWAIT_ACTION` só havia o texto livre, que passa por uma chamada de IA
  (custo, latência e risco de a IA classificar mal). Também não havia como dizer "essa palavra
  não me interessa": a entrada é gravada assim que o card sai, então ela ficava na lista.

## Decisão

- Palavra que já existe (mesmo `slug`: mesma palavra e mesmo sentido): o bot manda `📌 You already
  have *X* in your list.` com o sentido e o exemplo **salvos**, o convite a escrever uma frase, as
  opções 1 e 2 e "To send another word or command, type 0 or skip". Nada é regravado.
- `0` e `skip` em `AWAIT_ACTION` saem da palavra sem chamar a IA e sem apagar nada
  (`Acao.PULAR`, decidido na máquina de estados pura, ADR-0004).
- Opção 4 do menu, "Ignore this word, try another" (`Acao.IGNORAR`): apaga a entrada **só se** ela
  foi criada por aquela captura (`Sessao.entrada_criada_agora`) e o aluno ainda não escreveu frase
  nela. Palavra que já existia ou já foi praticada fica, e o bot avisa que ela continua na lista.
- Só `0`/`skip` (o que o bot anuncia) e frases inteiras (`ignore this word`, `ignore it`...) valem
  como texto; `stop`, `leave`, `ignore` ou `drop` sozinhas continuam indo para o roteamento, pois
  podem ser a palavra que o aluno quer aprender.

## Alternativas consideradas

- **Opção 4 só sai, sem apagar** — igual a `0`/`skip`; não resolve "não quero essa palavra na lista".
  O usuário escolheu descartar.
- **Opção 4 apaga sempre** — perderia palavra antiga ou já praticada por um número digitado sem
  querer; a proteção por `entrada_criada_agora` custa um campo booleano na sessão.
- **Checar a duplicata antes da IA** (comparando o texto digitado com a lista) — evitaria uma
  chamada, mas a IA é quem normaliza a forma ("mitigating" → "mitigate") e escolhe o sentido;
  fica para depois, se o custo pesar.
- **Reusar `eh_sair` (`stop`, `leave`, `quit`...) para sair da palavra** — sequestraria palavras
  comuns de vocabulário.

## Consequências

- Repetir uma palavra vira uma resposta curta e informativa, e o aluno segue direto para praticá-la.
- O menu ganha uma linha em todas as respostas; nos casos em que a opção 4 não apaga, ela só sai.
- `Sessao` ganha `entrada_criada_agora` (default falso: sessões antigas seguem válidas).
- `capture.gravar_entrada` passou a devolver `(entrada, criada_agora)`.
