# ADR-0029: Snapshot diário do Firestore em NDJSON no GCS, lido pelo BigQuery

- **Status:** Aceito
- **Data:** 2026-09-28

## Contexto

O dashboard de observabilidade (`spec/plano-dashboard.md`, M27–M30) precisa de métricas de
negócio — grupos, termos salvos por grupo/pessoa, admins × grupos, distribuição de lembretes —
que só existem hoje como o **estado atual** no Firestore, sem histórico: o Firestore guarda "o que
é verdade agora", não "o que era verdade ontem". Sem uma cópia diária em algum lugar consultável
por SQL, o painel do M30 não teria como mostrar tendência nenhuma, e um usuário custaria uma
leitura por documento por consulta (o Firestore não é feito para agregações desse tipo).

O M27 (ADR-0028) já resolveu a metade "eventos e falhas" com logs estruturados. Falta a metade
"fotografia do estado": quantos termos cada espaço tem, quem são as pessoas por trás dos números,
quais admins ativaram quais grupos.

## Decisão

1. **Quem tira a foto**: o próprio `Agendador` do bot (mesmo laço do M10/ADR-0012), uma vez por
   dia às 04:00 no fuso configurado. `Banco.obter_ultimo_snapshot`/`marcar_snapshot` (um documento
   `meta/snapshot`) garante que um restart não faz rodar duas vezes no mesmo dia. Sem
   `METRICS_BUCKET` configurado, o passo simplesmente não roda (`destino_de_metricas=None`) — nenhum
   ambiente de dev/CI tenta falar com o GCS.
2. **`montar_snapshot(banco, agora)`** (`app/services/snapshot.py`) é uma função **pura** sobre o
   `Banco`: lê cada espaço, cada entrada e cada frase **uma única vez** (o resultado é reaproveitado
   entre as tabelas de espaços/termos/pessoas/admins, para não duplicar leituras — seção 3.4 do
   plano) e devolve dataclasses imutáveis, uma lista por tabela. Testável 100% com `MemoryBanco`,
   sem rede.
3. **Onde grava**: NDJSON (`DestinoDeMetricas`, `app/services/metricas_destino.py`) num bucket
   próprio (`gs://…-vocabot-metrics`), particionado por dia no layout Hive
   (`tabela/dt=AAAA-MM-DD/parte-0.json`) — o formato que o BigQuery lê como **tabela externa**
   `NEWLINE_DELIMITED_JSON`, sem carga (`bq load`) nem custo de armazenamento duplicado no BigQuery.
   Os esquemas ficam versionados em `infra/bq/*.json`, um por tabela, e um teste
   (`test_esquema_do_bigquery_bate_com_os_campos_da_dataclass`) reprova se o código e o esquema
   divergirem.
4. **`Entry.autor_id`** e **`Profile.nome`** (novos campos, seção 7.1) fecham as duas lacunas que
   impediam a tabela de pessoas de existir de verdade: sem o primeiro, não dava para saber quem
   salvou uma palavra num grupo (frases e respostas já tinham autor desde o M16/M17); sem o
   segundo, a tabela de pessoas só teria o número mascarado, nunca um nome.
5. **`python -m scripts.snapshot`** roda o mesmo snapshot sob demanda, local com ADC — a primeira
   carga e a conferência do orçamento de leituras antes de ligar em produção.
6. **Privacidade** (decisão do usuário, 2026-09-27): número completo dos admins nas tabelas
   `espacos`/`admins` (são poucos e conhecidos); alunos só como `id_curto` (hash) + número
   mascarado — nunca o número completo.

## Alternativas consideradas

- **Cloud Run Job + Cloud Scheduler separado** — descartada: precisaria de imagem própria,
  Artifact Registry, SA com leitura no Firestore, e não teria acesso ao WAHA (loopback da VM);
  mais peças para o mesmo resultado.
- **`gcloud firestore export` gerenciado → load no BigQuery** — descartada: exporta por coleção
  com esquema aninhado ruim de consultar, e ainda cobraria a mesma leitura por documento sem dar
  controle sobre a agregação por espaço/pessoa.
- **Extensão "Stream Firestore to BigQuery" (Firebase)** — descartada: Cloud Functions por
  coleção, gatilho em toda escrita — acoplamento forte para um dado que só precisa ser diário.
- **Carga (`bq load`) em vez de tabela externa** — descartada por agora: tabela externa não exige
  processo de ingestão nem duplica armazenamento; revisitar se a performance de consulta no M30
  não for suficiente.

## Consequências

Fica fácil: consultar tendência de qualquer métrica de negócio por SQL no BigQuery Studio, sem
esperar o M30 (painel). O snapshot de hoje já é uma base sólida para as views do M30.

Fica difícil/pendente:
- **Reduzido do plano original**: a tabela `whatsapp` (contagem de grupos direto do WAHA) não
  entrou nesta primeira versão — precisa de uma chamada assíncrona ao canal que o `montar_snapshot`
  puro não faz; fica para quando o endpoint do WAHA (`GET /api/{session}/groups`) for confirmado
  (seção 3.3 do plano, `[confirmar]`). O campo `n_marcada` (quantas vezes uma pessoa foi marcada)
  também ficou de fora: só temos `Membro.marcado_em` (a última vez), não uma contagem — só
  `n_respondeu_marcada` (via `Resposta.marcado`) entrou.
- **Bytes estimados são uma aproximação** (fórmula oficial de tamanho de documento, seção 3.5 do
  plano): não conta índices automáticos. Testado contra um exemplo calculado à mão, não contra o
  Firestore real.
- **Orçamento de leituras**: hoje o snapshot lê cada documento (`entries`, `sentences`, `membros`,
  `respostas`) por espaço, uma vez. Se o volume crescer perto da cota grátis de 50k leituras/dia,
  a alternativa já prevista (seção 3.4) é trocar a contagem de frases por uma agregação `count()`
  em vez de listar — ainda não implementado, porque o volume atual está bem abaixo disso.
- **Infra ainda não provisionada**: `infra/setup_metricas.sh` (bucket + dataset) precisa rodar
  antes do primeiro snapshot ter onde gravar; até lá, a tentativa noturna falha em silêncio
  (`snapshot_falhou`, sem derrubar o bot) — o mesmo padrão do M23 (bucket de áudio) já ensinou que
  o deploy do código sozinho não basta.
- **Tabelas externas e views do BigQuery** (seção 3.6 do plano) ainda não foram criadas — é o
  próximo passo manual, depois da primeira execução do snapshot.
