# ADR-0002: Gestão de mudanças por ADR

- **Status:** Aceito
- **Data:** 2026-09-20

## Contexto

O projeto tem uma spec (`spec/spec-inicial.md`) que diz **o que** o sistema faz, mas nada que
registre **por que** cada escolha foi feita. As decisões iniciais (WAHA em vez da Cloud API, engine
GOWS em vez de WEBJS, Gemini no Vertex AI em vez de Claude, e2-micro em vez de Cloud Run) já
existiam só na cabeça de quem decidiu e no histórico de conversa — que não sobrevive ao tempo.

Sem esse registro, três coisas acontecem: a mesma discussão volta meses depois sem contexto; alguém
"conserta" uma restrição intencional achando que é descuido; e um ADR escrito por impulso vira ruído
porque não há critério do que merece registro.

Havia um diretório `docs/adr/` com template e um ADR, mas sem processo definido, sem gatilho claro
para criar um novo e sem nada que impedisse o diretório de apodrecer.

## Decisão

Toda decisão com consequência duradoura vira um ADR numerado em `docs/adr/`, no formato
`NNNN-titulo-curto.md` com quatro dígitos e zeros à esquerda.

O processo é operacionalizado em três camadas:

- **Skill `adr`** (`.claude/skills/adr/`) — carrega sozinha quando o contexto é uma escolha entre
  alternativas técnicas; define o gatilho, o passo a passo e o checklist de fechamento.
- **`docs/adr/README.md`** — índice de todos os ADRs, regras de numeração e tabela de status
  (`Proposto`, `Aceito`, `Substituído por ADR-NNNN`, `Descartado`).
- **`tests/test_adr.py`** — valida o que é mecânico (numeração sem buraco nem repetição, H1 batendo
  com o nome do arquivo, status válido, seções obrigatórias, índice completo). `make check` reprova
  um ADR malformado.

ADR aceito não se edita: decisão que muda vira ADR novo, e o antigo passa a
`Substituído por ADR-NNNN`.

## Alternativas consideradas

- **Numeração `ADR-1`, `ADR-2` sem zeros à esquerda** — foi o formato pedido originalmente, mas a
  ordenação alfabética quebra a partir do décimo ADR (`ADR-10` antes de `ADR-2`) em `ls`, no GitHub
  e no editor. Os quatro dígitos preservam a decisão (número sequencial legível) sem esse efeito.
- **Registrar o porquê na própria spec** — inchaça o contrato com justificativa histórica e força a
  reescrever o passado toda vez que uma decisão muda; a spec precisa descrever o presente.
- **Só o histórico de commits e PRs** — a mensagem de commit explica a mudança, não a alternativa
  rejeitada, e fica ilegível de recuperar meses depois.
- **Diretório de ADR sem testes** — foi o estado anterior. Sem validação automática, numeração
  duplicada e índice desatualizado aparecem na primeira semana movimentada.

## Consequências

- Fica fácil responder "por que X e não Y?" sem arqueologia, e fica registrado o que já foi
  rejeitado — alternativas descartadas não voltam como novidade.
- Fica mais caro tomar decisão grande: exige escrever a página antes de fechar o marco. É o custo
  pretendido.
- O índice do README vira ponto de manutenção manual; o teste evita que ele fique defasado, ao preço
  de reprovar `make check` quando alguém esquece a linha.
- A numeração de quatro dígitos limita o projeto a 9999 ADRs — irrelevante nesta escala.
- Revisitar se: o volume de ADRs triviais crescer (sinal de que o gatilho está frouxo), ou se o
  índice manual virar atrito real — nesse caso, gerá-lo por script no pre-commit.
