---
name: sdd
description: Desenvolvimento orientado a especificação (SDD, spec-driven development) — a spec do projeto é a fonte da verdade, o trabalho anda marco a marco, e divergências viram pergunta ou atualização da spec antes de virar código. Use SEMPRE que for implementar qualquer parte deste projeto, começar ou concluir um marco, quando a spec estiver ambígua/contraditória/desatualizada, quando o usuário pedir "seguir a spec", "próximo marco", "o que falta", ou quando for tomar uma decisão de design que a spec não cobre.
---

# SDD — Desenvolvimento orientado a especificação

A especificação deste projeto vive em `spec/spec-inicial.md`. Ela não é documentação a posteriori:
é o contrato que define o que existe, o que está fora de escopo e em que ordem as coisas são
entregues. Código que contraria a spec é bug — mesmo que funcione.

## O ciclo

1. **Ler a seção relevante da spec antes de escrever qualquer código.** Não a spec inteira toda vez;
   a seção do marco atual, mais as seções que ela referencia (contratos de dados, formato de
   mensagem, estrutura de pastas).
2. **Derivar os critérios de aceite.** Todo marco na spec tem um critério ("os testes de todas as
   transições passam", "o `.txt` bate byte a byte"). Esse critério é o teste a escrever primeiro
   (ver a skill `tdd`).
3. **Implementar o mínimo que satisfaz o marco.** Não antecipe o marco seguinte: a spec define a
   ordem por um motivo (cada marco é revisável isoladamente).
4. **Parar ao fim do marco** e reportar: o que foi entregue, como o critério de aceite foi
   verificado, e o que ficou de fora. Só avance com aprovação explícita.
5. **Commitar ao fim de cada marco** (ver a skill `git-workflow`).

## Quando a spec e a realidade divergem

Isso vai acontecer — a spec foi escrita antes do código existir, e documentação externa (WAHA,
Vertex AI, SDKs) muda. A regra é: **a divergência nunca é resolvida em silêncio no código.**

| Situação | O que fazer |
|---|---|
| A spec é ambígua (duas leituras razoáveis) | Perguntar antes de escolher. Não inventar. |
| A spec contradiz a documentação oficial atual (ID de modelo, nome de endpoint, variável de ambiente) | Confirmar na documentação, mostrar a evidência, propor o ajuste e esperar aprovação. |
| A spec não cobre um detalhe pequeno e sem consequência | Decidir, implementar e **mencionar no relatório do marco**. |
| A spec pede algo que parece errado ou perigoso | Dizer por quê, em uma ou duas frases, e esperar. |
| A decisão tem consequência duradoura | Registrar um ADR em `docs/adr/` (ver `docs/adr/README.md`). |

Quando uma decisão muda o contrato, **atualize a spec no mesmo commit que muda o código**. Spec
desatualizada é pior que spec ausente: ela mente com autoridade.

## Contratos vêm antes de implementações

A spec define modelos Pydantic, esquemas do Firestore, o formato exato do arquivo do Anki e as
interfaces (`Channel`, `Repository`, `LLMProvider`). Implemente **primeiro o contrato** (o tipo, o
Protocol, o modelo) e só depois a implementação concreta. Isso torna possível ter um fake em memória
para cada dependência externa — que é o que permite testar sem rede, sem credencial e sem custo.

Formatos marcados como fixos na spec (o cabeçalho do export do Anki, por exemplo) são testados byte
a byte, com o arquivo esperado versionado em `tests/fixtures/`.

## O que NÃO fazer

- Implementar features "que fazem sentido" mas estão explicitamente fora de escopo (revisão
  espaçada, áudio, multiusuário, painel web, conversa livre).
- Adicionar dependências, serviços ou recursos de nuvem que a spec não prevê, sem perguntar.
- Pular o critério de aceite porque "obviamente funciona".
- Avançar dois marcos de uma vez para "economizar tempo".

## Ao começar uma sessão de trabalho

Diga em uma linha em que marco estamos, o que o critério de aceite exige e qual é o primeiro teste
que você vai escrever. Se não estiver claro qual é o marco atual, olhe o histórico de commits e a
tabela da seção 9 da spec — e, na dúvida, pergunte.
