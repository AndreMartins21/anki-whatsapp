# Architecture Decision Records (ADR)

Registro curto de decisões técnicas com consequência duradoura: **o que** foi decidido, **por quê**,
e o que foi descartado. Um ADR evita que a mesma discussão volte daqui a três meses sem contexto.

A skill `adr` (em `.claude/skills/adr/`) descreve o processo completo. Este arquivo é a referência
operacional: numeração, status e o índice.

## Índice

| ADR | Título | Status | Data |
|---|---|---|---|
| [0001](0001-stack-do-mvp.md) | Stack do MVP (WAHA + Gemini no Vertex AI + VM e2-micro) | Aceito | 2026-09-20 |
| [0002](0002-gestao-de-mudancas-por-adr.md) | Gestão de mudanças por ADR | Aceito | 2026-09-20 |
| [0003](0003-firestore-como-banco-atras-de-repository.md) | Firestore (modo nativo) como banco, atrás de uma interface Repository | Aceito | 2026-09-20 |
| [0004](0004-maquina-de-estados-pura.md) | Máquina de estados como função pura que devolve uma ação | Aceito | 2026-09-20 |

## Quando escrever um

Escreva um ADR quando a decisão:

- é difícil de reverter (banco, hospedagem, provedor de IA, formato de dados exportado);
- restringe o trabalho futuro (limite de memória da VM, "não usar engine WEBJS");
- foi tomada entre alternativas reais, e alguém razoável escolheria diferente.

Não escreva para escolhas triviais ou facilmente reversíveis (nome de variável, ordem de funções,
refatoração local, bump de dependência).

## Numeração

Arquivos seguem `NNNN-titulo-curto.md`, com quatro dígitos e zeros à esquerda — `0001`, `0002`,
... `0042`. O zero-padding mantém a ordenação alfabética igual à ordem cronológica em qualquer
ferramenta (`ls`, GitHub, editor). `0000-template.md` é o molde e não conta como decisão.

O próximo número sai de:

```bash
ls docs/adr/ | grep -E '^[0-9]{4}-' | sort | tail -1
```

Números nunca são reaproveitados, nem quando um ADR é descartado.

## Status

| Status | Significado |
|---|---|
| `Proposto` | Escrito, ainda não aprovado nem implementado. |
| `Aceito` | Vale agora. |
| `Substituído por ADR-NNNN` | Não vale mais; o ADR indicado explica o que vale. |
| `Descartado` | Considerado e rejeitado; fica registrado para não ser reproposto. |

## Como

1. Copie `0000-template.md` para `NNNN-titulo-curto.md` (número sequencial).
2. Preencha. Seja breve: uma página basta.
3. Acrescente a linha no índice acima.
4. Commite o ADR junto com o código que o implementa.
5. ADR aceito **não se edita** — se a decisão mudar, crie um novo ADR e marque o antigo como
   `Substituído por ADR-NNNN`.

`tests/test_adr.py` verifica o que é mecânico: numeração, título, status, seções obrigatórias e se o
índice está completo. `make test` reprova um ADR malformado.
