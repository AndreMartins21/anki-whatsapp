# ADR-0010: Interface do bot em inglês, com a tradução como única exceção

- **Status:** Aceito
- **Data:** 2026-09-22

## Contexto

Até o M8, todo texto voltado ao aluno (`app/messages.py`, e os campos `classe`/`nota` que a IA
gera em `app/services/prompts.py`) era em PT-BR — a regra de ouro 4 do `CLAUDE.md` e a spec §3.5
diziam isso explicitamente. O pedido do M9 é imersão: o aluno pratica lendo e recebendo feedback
em inglês o tempo todo, não só nas frases de exemplo.

## Decisão

Toda mensagem do bot passa a ser em inglês — menus, avaliações, confirmações, comandos e o texto
livre que a IA escreve nas intenções `pedido`/`fora_do_escopo` (ADR-0009). A única exceção é a
linha 🇧🇷 do card inicial, com a tradução literal da palavra/expressão, porque é o único ponto em
que o aluno precisa da ponte direta para o português. Os prompts (`app/services/prompts.py`)
continuam escritos em PT-BR (é assim que o autor do projeto os lê e mantém), mas a instrução ao
modelo muda de "explique em português do Brasil" para "escreva tudo em inglês; só `traducao` é em
PT-BR". Como consequência direta, os campos livres que a IA preenche e que o bot usa como estão —
`Explanation.classe` (ex.: "verb" em vez de "verbo") e `Explanation.nota`/`Entry.nota` — também
passam a vir em inglês, porque são exibidos ao aluno sem tradução.

## Alternativas consideradas

- **Inglês para o conteúdo de ensino, PT-BR para o operacional** (menus, confirmações do sistema,
  erros) — foi a opção descartada na conversa inicial com o usuário em favor de "tudo em inglês,
  exceto a tradução": um menu em português no meio de uma frase em inglês quebra a imersão, e
  mistura o idioma da "voz do sistema" com o da "voz do professor" sem necessidade.
- **i18n de verdade (arquivo de strings, campo de idioma no `Profile`)** — o projeto é de um único
  usuário com um único idioma-alvo (seção 1); um sistema de internacionalização geral não paga o
  custo de manutenção para esse escopo. Revisitar só se o projeto ganhar mais de um usuário/idioma.

## Consequências

- Fácil: o aluno já pratica leitura em inglês em cada resposta do bot, não só nas frases de
  exemplo; a regra "todo texto ao usuário fica em `app/messages.py`" continua valendo, só muda o
  idioma dentro do arquivo.
- Difícil: `Entry.classe` e `Entry.nota` de palavras salvas **antes** do M9 continuam em PT-BR
  (Pydantic não migra dados antigos); o card e o cartão do Anki de uma entrada antiga versus uma
  nova ficam com o idioma misturado até o aluno praticar de novo essa palavra (o que reescreve
  `classe`/`nota`) ou apagá-la e recriar. Não há migração automática — é um MVP de um usuário só, e
  o custo de escrever e testar uma migração não compensa para um punhado de entradas.
- O formato fixo do export do Anki (spec §7.3, `#notetype:Inglês – Vocabulário`, nomes de coluna)
  **não muda** — só o conteúdo dos campos `Traducao` e `Nota` passa a vir em inglês para entradas
  novas, como acima.
- Revisitar se: o usuário quiser voltar a ter partes em PT-BR (ex.: se achar que perde clareza no
  feedback de erros) ou se o projeto ganhar um segundo usuário com outra preferência de idioma.
