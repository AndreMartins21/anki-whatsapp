# ADR-0003: Firestore (modo nativo) como banco, atrás de uma interface Repository

- **Status:** Aceito
- **Data:** 2026-09-20
- **Fonte:** `spec/spec-inicial.md` seções 2, 7.1 e 8.2

## Contexto

O bot guarda pouco dado (palavras, frases, uma sessão de conversa, ids de mensagens já vistas) para
um único usuário, e roda numa VM `e2-micro` de 1 GB de RAM. Precisamos de: persistência que sobreviva
a rebuild/recriação da VM, deduplicação atômica de mensagens do webhook (o WAHA pode reentregar), expiração
automática dos ids já vistos, e custo praticamente zero.

"Firebase" aqui é só a marca: usamos o **Cloud Firestore**, produto do próprio GCP, pelo cliente
`google-cloud-firestore`, autenticado pela conta de serviço da VM (`roles/datastore.user`). Não há
projeto Firebase, SDK Firebase nem chave de API.

## Decisão

Usamos o Firestore em modo nativo como banco. A aplicação nunca fala com ele direto: toda persistência
passa pela interface `Repository` (`app/repo/base.py`), com `FirestoreRepository` em produção e
`MemoryRepository` nos testes e no simulador. A deduplicação de mensagens e o cache de LID→número
também moram no `Repository`.

## Alternativas consideradas

- **SQLite no disco da VM** — é a opção mais simples e não custa nada, mas o dado morre junto com o disco
  (recriar a VM apaga o histórico), não há TTL nativo e acopla o estado ao host. Continua sendo a
  alternativa mais forte se o Firestore virar um incômodo.
- **Cloud SQL (Postgres/MySQL)** — custo fixo mensal sem nível gratuito contínuo; desproporcional para
  poucos milhares de linhas.
- **Objetos no Cloud Storage (JSON)** — barato, mas sem consulta por status nem transação; dedup
  dependeria de pré-condições de geração por objeto, e listar/filtrar entradas viraria varredura.
- **Bigtable / Spanner** — pensados para escala que não existe aqui e sem nível gratuito.

## Consequências

- Fácil: dado durável e independente da VM; TTL nativo em `processed.expira_em`; nível gratuito cobre o
  uso com folga; testes rápidos com `MemoryRepository`.
- Difícil: o cliente síncrono do Firestore bloqueia — chamadas a partir de código `async` (webhook) vão
  para threadpool. Consultas com filtro + ordenação exigem índice composto; evitamos filtrando por status
  no servidor e ordenando em Python (volume pequeno). Cobrir o `FirestoreRepository` de verdade exige o
  emulador; o mesmo teste de contrato roda contra os dois repositórios quando `FIRESTORE_EMULATOR_HOST` está definido.
- Revisitar se: o Firestore causar atrito operacional desproporcional, aparecer um segundo usuário com
  consultas relacionais, ou a cota gratuita deixar de cobrir o uso.
