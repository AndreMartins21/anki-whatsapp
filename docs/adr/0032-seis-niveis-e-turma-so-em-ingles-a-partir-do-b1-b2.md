# ADR-0032: Seis níveis e turma só em inglês a partir de B1-B2

- **Status:** Aceito
- **Data:** 2026-10-01

## Contexto

O ADR-0010 deixou a tradução em PT-BR (🇧🇷) como única exceção ao inglês, para todo nível. Numa
turma de B1-B2 para cima isso atrapalha o objetivo da aula: o aluno lê o português em vez de pensar
em inglês. Além disso só existiam três níveis (A2-B1, B1-B2, B2-C1), sem como descrever uma turma
iniciante (A1-A2) nem uma avançada (C1-C2, C2).

## Decisão

1. **Seis níveis:** `A1-A2`, `A2-B1`, `B1-B2`, `B2-C1`, `C1-C2` e `C2` (`NivelUsuario`), valendo no
   `/level` do privado e no `!level` do grupo. Cada um tem calibração própria no prompt.
2. **Só no grupo, de B1-B2 para cima, nada em português na tela** (`nivel_so_ingles`): card, outros
   sentidos (`↔️`), cabeçalhos de exemplos/sinônimos/avaliação e o `!list`, que mostra a definição
   (cortada em 70 caracteres) no lugar da tradução. A1-A2 e A2-B1 mantêm a linha 🇧🇷.
3. **O privado não muda**, em nenhum nível.
4. **A `traducao` continua sendo gerada e gravada.** Ela decide a identidade do sentido
   (`resolver_slug`/`mesma_traducao`, ADR-0023), vai para a planilha e para os prompts. Só deixa de
   aparecer. O `Router` calcula `Deps.so_ingles` a cada mensagem a partir do perfil da turma, então
   `!level` vale já na mensagem seguinte.

## Alternativas consideradas

- **Parar de gerar a tradução em turmas avançadas.** Descartada: quebraria a identidade do sentido
  e a planilha, e o ganho (alguns tokens) é pequeno.
- **Uma opção por turma (`!portuguese on|off`) em vez de derivar do nível.** Descartada: mais um
  conceito para o professor configurar; o nível já diz o que o aluno precisa.
- **Manter só três níveis.** Descartada: o usuário tem turmas de A1-A2 a C2.

## Consequências

- Complementa o ADR-0010 (a exceção do português vira condicional) e o ADR-0031 (`!level` aceita os
  seis níveis). Ambos seguem Aceitos.
- O nível padrão do ambiente (`USER_LEVEL`, B1-B2) faz **todo grupo existente passar a ver só inglês**
  até o professor rodar `!level A2-B1` (ou A1-A2). Avisar o usuário no deploy.
- Perfis já gravados continuam válidos (os três níveis antigos estão no `Literal`).
- A explicação em português de perguntas em turma iniciante (M36) é outra exceção, tratada no ADR
  correspondente.
