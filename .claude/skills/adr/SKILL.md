---
name: adr
description: Gestão de mudanças por ADR (Architecture Decision Record) — toda decisão de arquitetura, escolha de tecnologia, contrato ou restrição duradoura vira um markdown numerado em docs/adr/. Use SEMPRE que escolher entre alternativas técnicas reais (biblioteca, provedor, banco, formato de arquivo, protocolo, estrutura de pastas), quando mudar ou substituir uma decisão já registrada, quando o usuário disser "registra essa decisão", "por que a gente escolheu X", "cria um ADR", "documenta a mudança de arquitetura", ou quando uma escolha for difícil de reverter e alguém razoável escolheria diferente.
---

# ADR — Registro de decisões de arquitetura

Um ADR é uma página curta que responde três perguntas: **o que** foi decidido, **por quê**, e **o
que foi descartado**. Ele existe para que a mesma discussão não volte daqui a três meses sem
contexto — e para que quem herdar o código entenda a restrição antes de "consertar" algo que é
intencional.

Os ADRs deste projeto vivem em `docs/adr/`. O índice e as regras operacionais estão em
`docs/adr/README.md` — leia antes de criar o primeiro ADR de uma sessão.

## Quando escrever um

Escreva quando a decisão tiver **pelo menos duas** destas características:

- é difícil ou cara de reverter (banco, hospedagem, provedor de IA, formato exportado, protocolo);
- restringe o trabalho futuro ("não usar engine WEBJS", "1 GB de RAM", "sem dependência de rede nos testes");
- foi tomada entre alternativas reais, e alguém razoável escolheria diferente;
- explica algo que parece errado no código até você conhecer o motivo.

**Não** escreva ADR para: nome de variável, ordem de funções, refatoração local, bump de versão de
dependência, correção de bug. Isso é ruído — e ruído esvazia o valor do diretório.

Na dúvida entre escrever e não escrever: escreva. Um ADR curto custa cinco minutos; uma decisão
perdida custa uma tarde de arqueologia.

## Como criar

1. **Descubra o próximo número** (nunca chute):

   ```bash
   ls docs/adr/ | grep -E '^[0-9]{4}-' | sort | tail -1
   ```

   O próximo é esse + 1, com quatro dígitos e zeros à esquerda: `0001`, `0002`, ... `0042`.

2. **Copie o template** para `docs/adr/NNNN-titulo-curto.md`:

   ```bash
   cp docs/adr/0000-template.md docs/adr/0007-fila-de-mensagens.md
   ```

   O slug é curto, em minúsculas, com hífens, sem acento: descreve a decisão, não o problema
   (`0007-fila-de-mensagens.md`, não `0007-mensagens-estao-lentas.md`).

3. **Preencha.** Uma página basta. O H1 é `# ADR-NNNN: <título>` e o número tem que bater com o nome
   do arquivo — há teste verificando.

4. **Adicione a linha no índice** do `docs/adr/README.md`. Também há teste verificando.

5. **Commite o ADR junto com o código que o implementa** — não antes, não depois. Se a decisão ainda
   não virou código, o status é `Proposto` e ele pode ir sozinho.

## Status e ciclo de vida

| Status | Significado |
|---|---|
| `Proposto` | Decisão escrita, ainda não aprovada nem implementada. |
| `Aceito` | Vale agora. É o estado normal de um ADR ativo. |
| `Substituído por ADR-NNNN` | Não vale mais; o ADR indicado explica o que vale. |
| `Descartado` | Foi considerado e rejeitado; fica registrado para não ser reproposto. |

**ADR aceito não se edita.** Se a decisão mudar, crie um ADR novo que explique a mudança e edite o
antigo apenas para trocar o status para `Substituído por ADR-NNNN`. Reescrever a história apaga
justamente a informação que o ADR existe para preservar: que já pensamos diferente, e por quê.

Correção de typo ou link quebrado é a única edição aceitável num ADR aceito.

## Relação com a spec

A spec (`spec/spec-inicial.md`) diz **o que o sistema faz**; o ADR diz **por que foi construído
assim**. Eles não competem:

- Mudou um contrato (modelo de dados, formato de mensagem, variável de ambiente)? Atualize a spec no
  mesmo commit — ver a skill `sdd`.
- A mudança de contrato veio de uma escolha entre alternativas? Além da spec, escreva o ADR e
  referencie a seção da spec afetada no campo `Fonte`.

Um ADR nunca substitui a atualização da spec, e a spec nunca carrega a justificativa longa.

## Antes de fechar

- [ ] Número sequencial correto, sem buraco e sem repetição.
- [ ] H1 bate com o nome do arquivo.
- [ ] Status válido e data no formato `AAAA-MM-DD`.
- [ ] Seções `Contexto`, `Decisão`, `Alternativas consideradas` e `Consequências` preenchidas.
- [ ] Pelo menos uma alternativa real, com o motivo da rejeição.
- [ ] Consequências dizem o que ficou **difícil**, não só o que ficou fácil.
- [ ] Condição de revisão explícita ("revisitar se ...").
- [ ] Linha adicionada ao índice do `docs/adr/README.md`.
- [ ] Nenhum segredo, token, número de telefone ou ID de cliente no texto.
- [ ] `make test` passa (os testes de `tests/test_adr.py` validam tudo acima que é mecânico).
