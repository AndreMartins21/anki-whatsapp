# ADR-0028: Logs estruturados com eventos e um handler para o Cloud Logging

- **Status:** Aceito
- **Data:** 2026-09-27

## Contexto

O dashboard de observabilidade (`spec/plano-dashboard.md`, M27–M30) precisa saber, sem entrar no
Firestore nem na VM à mão: quantas falhas o sistema teve, quantos lembretes foram enviados,
quantas revisões terminaram, se a IA está lenta ou rejeitando respostas, e se o WhatsApp está no
ar. Hoje os logs (`app/logging_config.py`) são uma linha JSON por evento, mas em texto livre — sem
um campo que diga "isto foi um lembrete enviado" de um jeito que uma consulta possa contar. E,
mais grave: **os logs não saem da VM**. O `docker-compose.yml` não define um driver de log por
serviço, então vale o `json-file` padrão configurado em `infra/vm/startup.sh` (com rotação, para o
disco de 30 GB não estourar) — tudo fica só ali, lido por `infra/logs.sh`/`docker compose logs`.

A primeira ideia (registrada no rascunho do plano) era trocar o driver do Docker para `gcplogs`
nos dois serviços. Ao implementar, a documentação oficial confirmou um problema real: o driver
`gcplogs` **não implementa leitura** ("this log driver does not implement a reader so it is
incompatible with `docker logs`"). Trocar o driver quebraria exatamente as ferramentas que hoje
são usadas para depurar a única VM de produção (`infra/logs.sh`, `infra/smoke_test.sh`, e o
runbook manual de depuração via SSH: `docker compose logs --since Nh bot`).
Instalar o Ops Agent (a alternativa "oficial" da Google para isso) é pesado demais para uma
`e2-micro` de 1 GB de RAM que já reparte memória entre WAHA e bot (seção 10.7 da spec).

## Decisão

1. **Catálogo de eventos** (seção 12 da spec): pontos de negócio importantes (mensagem recebida,
   lembrete enviado/adiado/desistido, revisão concluída/respondida, marcação expirada, chamada à
   IA, chamada ao Cloud TTS, grupo ativado/desativado/pendente, saída de grupo pendente, aviso de
   "sem plano", status do WAHA, início do processo) chamam `registrar_evento(logger, nome,
   **campos)`, que grava o campo `evento` e só os campos de uma lista branca
   (`CAMPOS_DE_EVENTO`) — nunca texto do aluno, número completo ou payload.
2. **Transporte para a nuvem, revisado**: nada de trocar o driver do Docker. Em vez disso, o
   processo do **bot** (só ele — o `waha` continua só no `json-file` local) ganha um **segundo
   handler de logging**, da biblioteca `google-cloud-logging` (`uv add`), montado em paralelo ao
   `StreamHandler` de stdout de sempre — que não muda em nada. `configurar_logs` aceita esse
   handler como parâmetro (`handler_extra`), nunca o constrói sozinho: o módulo continua sem rede
   nem credencial nos testes (convenção do projeto). Autenticação pela mesma conta de serviço da
   VM (`vocabot-vm`, já tem `roles/logging.logWriter`), sem segredo novo. Handler padrão da
   biblioteca (`BackgroundThreadTransport`): não bloqueia a resposta ao webhook do WAHA.

## Alternativas consideradas

- **Driver `gcplogs` do Docker** — descartada: sem leitura via `docker logs`/`docker compose
  logs`, quebraria `infra/logs.sh` e `infra/smoke_test.sh` na única VM de produção.
- **Ops Agent (`google-cloud-ops-agent`)** — descartada: outro processo rodando full-time na
  `e2-micro`, concorrendo por memória com WAHA e bot (spec 10.7/10.8 já tratam a RAM como escassa).
- **Handler `google-cloud-logging` também no `waha`** — não é possível: o WAHA não é Python, não
  há como injetar um handler no processo de outro container.
- **Não mandar nada para a nuvem agora** — adiava demais o dashboard (M27 inteiro dependeria de
  entrar na VM à mão para ver falhas), e o catálogo de eventos (item 1) já vale sozinho para os
  logs locais.

## Consequências

Fica fácil: contar/filtrar por `evento` em qualquer consulta (local, ou no Log Analytics depois
que o handler estiver ligado), sem tocar em `docker-compose.yml` nem em `infra/vm/startup.sh`, e
sem arriscar o runbook de depuração que já existe. `waha` continua só localmente logado — suas
falhas relevantes já aparecem via `waha_status` (o bot loga a própria mudança de status da sessão)
e via as exceções que o bot registra ao redor de cada chamada ao canal.

Fica difícil/pendente: falta confirmar em produção o formato exato do `jsonPayload` que o
`CloudLoggingHandler` produz (se os campos extras chegam como `jsonPayload` estruturado ou só como
texto — ver `spec/plano-dashboard.md` seção 2.3); a biblioteca `google-cloud-logging` é uma
dependência nova (`uv add`), a acompanhar no tamanho da imagem do bot (limite de RAM da VM). Se o
formato chegar ruim, o ajuste é só na construção do handler (uma função), não no catálogo de
eventos. Revisitar quando o M28 (snapshot no BigQuery) e o M30 (painel) forem implementados — é
quando o formato real dos eventos passa a ser consultado de verdade.
