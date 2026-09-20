# ADR-0006: Conversa em segundo plano, serializada, com código bloqueante em threads

- **Status:** Aceito
- **Data:** 2026-09-20
- **Fonte:** `spec/spec-inicial.md` seções 5.6 e 8.1

## Contexto

Responder ao aluno leva segundos: chamadas à IA, mais o atraso deliberado de 1 a 2 s antes de cada
mensagem (seção 5.6, reduz o risco de bloqueio da conta). O WAHA espera um `200` do webhook e reenvia o
evento se demora. Firestore e IA usam clientes síncronos, e o canal (`Channel`) é assíncrono. O aluno
pode mandar duas mensagens em sequência, e a máquina de estados lê e grava uma sessão única.

## Decisão

- O webhook filtra (fromMe, grupo, allowlist, dedup), marca como lida e responde `200` na hora; a conversa roda numa
  `BackgroundTask`. Toda exceção ali é capturada e vira a mensagem curta de erro.
- Os fluxos (`app/flows/`) são `async`; o que bloqueia (Firestore, IA) roda em thread via
  `asyncio.to_thread`, sem travar o event loop.
- O `Router` usa um `asyncio.Lock`: uma mensagem por vez, na ordem de chegada, para a sessão nunca ser lida
  e gravada por duas mensagens ao mesmo tempo.
- `Conversa` concentra o comportamento humano: "digitando…", espera aleatória de 1–2 s, no máximo 3
  mensagens seguidas sem resposta do aluno, e destino fixo no chat do número permitido.
- Uma falha da IA responde "não consegui falar com a IA" e deixa a sessão como estava, para o aluno repetir.

## Alternativas consideradas

- **Processar dentro da requisição** — mais simples, mas com IA + atrasos o webhook passaria de
  vários segundos; o WAHA reenviaria o evento (a dedup evitaria o duplo processamento, mas o ruído ficaria).
- **Fluxos síncronos rodando inteiros em threadpool** — combina com a frase da spec, mas exige uma ponte
  thread→loop a cada envio pelo canal assíncrono, e complica o simulador de terminal e os testes.
- **Fila externa (Cloud Tasks, Pub/Sub)** — serviço novo, fora do que a spec permite, para um único usuário.

## Consequências

- Fácil: testar a conversa inteira com fakes e sem espera real (`dormir` e `atraso` são injetáveis); o
  simulador reaproveita o mesmo `Router`.
- Difícil: se o processo cair depois do `200`, a mensagem já marcada como processada se perde (o aluno
  reenvia). A serialização é por processo — vale porque há uma instância só; com mais de uma, a sessão precisaria de trava
  no banco.
- Revisitar se: houver mais de um usuário ou mais de uma instância do bot.
