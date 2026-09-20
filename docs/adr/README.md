# Architecture Decision Records (ADR)

Registro curto de decisões técnicas com consequência duradoura: **o que** foi decidido, **por quê**,
e o que foi descartado. Um ADR evita que a mesma discussão volte daqui a três meses sem contexto.

## Quando escrever um

Escreva um ADR quando a decisão:

- é difícil de reverter (banco, hospedagem, provedor de IA, formato de dados exportado);
- restringe o trabalho futuro (limite de memória da VM, "não usar engine WEBJS");
- foi tomada entre alternativas reais, e alguém razoável escolheria diferente.

Não escreva para escolhas triviais ou facilmente reversíveis (nome de variável, ordem de funções).

## Como

1. Copie `0000-template.md` para `NNNN-titulo-curto.md` (número sequencial).
2. Preencha. Seja breve: uma página basta.
3. ADR aceito **não se edita** — se a decisão mudar, crie um novo ADR com status `Aceito` e marque o
   antigo como `Substituído por ADR-NNNN`.
