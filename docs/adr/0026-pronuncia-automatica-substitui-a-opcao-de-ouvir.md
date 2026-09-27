# ADR-0026: Pronúncia automática ao explicar a palavra, substituindo a opção de ouvir no menu

- **Status:** Aceito
- **Data:** 2026-09-27

## Contexto

Desde o M23 (ADR-0024), ouvir a pronúncia de uma palavra era **sob demanda**: o aluno escolhia a
opção 1 do menu (ou usava `/listen`), e só então o bot sintetizava e mandava as duas notas de voz.
A decisão foi deliberada — sintetizar sempre gastaria TTS e as duas notas de voz junto do card já
usariam 2 dos 3 slots do limite de mensagens seguidas (seção 5.6), para um termo que o aluno talvez
nunca quisesse ouvir.

Na prática, isso deixa a pronúncia **escondida atrás de um passo extra**: a maioria dos alunos
nunca escolhe a opção 1, mesmo sendo um dos jeitos mais diretos de aprender a falar a palavra
certo. O áudio já existe, já está cacheado (`ServicoAudio`/GCS) e o custo do TTS é pequeno perto do
ganho de aprendizado — o cache já resolve boa parte do problema de custo que a decisão original
tentava evitar (só a primeira vez que qualquer aluno pede aquele termo sintetiza de verdade).

## Decisão

**A pronúncia em áudio vira automática**, mandada logo depois de explicar a palavra (nova ou já
existente), sem precisar de nenhuma escolha do menu. A opção 1 (ouvir) **sai do menu**; as opções
2 a 5 continuam com os mesmos números de sempre — o menu só passa a começar no 2, sem renumerar
nada que o aluno já tenha decorado.

`app/flows/pronuncia.py:ouvir` ganha um parâmetro `anunciar`: `True` (o padrão, usado por
`/listen`) mantém o comportamento de sempre — avisa se o áudio não está disponível neste ambiente,
com um texto antes das vozes. `False` (automático) fica **em silêncio** quando o serviço de áudio
não está configurado (ninguém pediu explicitamente, e a explicação já dita basta), mas ainda avisa
numa falha de verdade (TTS, Storage, WhatsApp), porque aí alguma coisa quebrou e ficar calado
pareceria o bot ignorando o aluno.

O orçamento de mensagens (seção 5.6) fecha em 3: a explicação + o menu (1 mensagem, como sempre) e
as duas vozes (2 mensagens) — o mesmo total de antes, só sem o segundo turno que a opção 1 exigia.

## Alternativas consideradas

- **Manter sob demanda, só melhorar a visibilidade da opção 1** (destacar mais no menu, lembrete
  periódico) — mais simples e não contraria a ADR-0024, mas não resolve o problema real: a opção já
  está bem visível no menu e a maioria não a escolhe mesmo assim.
- **Automático só na primeira vez que a palavra é salva, sob demanda depois** — evita repetir áudio
  em revisões futuras da mesma entrada, mas complica a regra (dois comportamentos diferentes para o
  mesmo `ouvir`) para um ganho pequeno, já que o cache já torna repetições baratas.
- **Renumerar o menu para 1-4** (examples=1, synonyms=2, save=3, ignore=4) — ficaria mais "limpo"
  sem o buraco no número 1, mas re-treina um hábito que os alunos ativos já têm (`4` = salvar,
  `5` = ignorar, inclusive documentado em `/help` e no `spec/plano-turmas.md`) sem nenhum ganho
  funcional; manter os números de sempre é estritamente menos disruptivo.

## Consequências

- Fácil: `ouvir_da_sessao` e `Acao.OUVIR` somem (código morto depois da opção 1 deixar de existir);
  `ja_existe()` e o menu único passam a compartilhar a mesma numeração a partir do 2, sem um menu
  "de depois do áudio" separado como havia entre o M23 e o M25.
- Difícil: todo ambiente sem `AUDIO_BUCKET`/fora de produção (`app_env != "prod"`, `_criar_audio`
  em `app/main.py`) explica uma palavra em silêncio quanto ao áudio — o que é o comportamento
  certo (não é uma falha, é o recurso indisponível ali), mas exige lembrar essa distinção ao ler
  `pronuncia.ouvir`: `d.audio is None` não é o mesmo tipo de "erro" que uma exceção durante a
  síntese.
- Custo de TTS sobe: toda palavra nova ou reaberta sintetiza (na primeira vez; depois é cache), não
  só as que alguém pedia para ouvir — aceitável dado o tamanho do cache compartilhado entre espaços
  e o valor de aprendizado; revisitar se o volume de palavras únicas crescer a ponto de o custo
  incomodar.
