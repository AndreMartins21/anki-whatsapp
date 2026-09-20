# ADR-0008: Continuar na GCP e manter a saída portátil (casa ou Oracle) para depois do trial

- **Status:** Aceito
- **Data:** 2026-09-20
- **Fonte:** `spec/spec-inicial.md` seção 10.8; revisita o custo assumido no [ADR-0001](0001-stack-do-mvp.md)

## Contexto

A hospedagem é a única linha do projeto que não é gratuita, e o incômodo é pequeno em dinheiro mas real: o
usuário quer custo zero ou "pífio". Tudo o mais fica em cota gratuita (Firestore, Storage, Secret Manager) ou
custa centavos (Vertex AI). O que sobra é o **IP externo da VM**: US$ 0,005/hora, ou cerca de US$ 3,60/mês.
A `e2-micro` e o disco standard de 30 GB seguem no nível gratuito. A documentação do Google é ambígua sobre o
free tier cobrir ou não o IP externo — a resposta confiável é a fatura real, no SKU "External IP Charge on a
Standard VM", alguns dias depois do primeiro deploy.

Uma constatação muda o leque de opções: **o bot não precisa de nenhuma conexão de entrada**. O WAHA abre a
conexão com o WhatsApp de dentro para fora, o webhook é interno à rede do Docker e o painel do QR é acessado
por túnel IAP. O IP externo existe só para a VM **sair** para a internet (WhatsApp, Docker Hub, `apt`) — na GCP,
uma VM sem IP externo não tem saída a menos que se acrescente Cloud NAT, que custa mais que o próprio IP e
adiciona uma peça para operar. Numa máquina doméstica esse papel já é do roteador, e aí nenhum IP público é preciso.

Caminhos levantados em 2026-09-20 (preços e limites mudam; reconferir antes de decidir):

| Caminho | Custo | Ressalvas |
|---|---|---|
| **GCP, como está** | US$ 0 a 3,60/mês (só o IP) | Pronto e funcionando; coberto pelos créditos do trial por 90 dias |
| **Máquina em casa** (Raspberry Pi, mini PC, notebook velho) | Só eletricidade (~R$ 5 a 15/mês) | Cai com queda de luz ou de internet; exige sair do Firestore/Vertex (ver abaixo) |
| **Oracle Cloud Always Free** | Zero, com 1 IP público incluído | Free tier ARM caiu de 4 OCPU/24 GB para 2/12 em junho/2026; "out of capacity" é comum; há relatos de contas encerradas sem aviso |
| **VPS barato** (Hetzner e afins) | ~€ 3 a 4/mês | Previsível, mas não é gratuito — troca um custo pequeno por outro |
| **GCP sem IP externo, com Cloud NAT** | Mais caro que o IP | Descartado: custa mais e a spec (10.8) proíbe Cloud NAT |

Sair da GCP obriga a trocar três coisas, porque fora dela não há identidade automática da VM para autenticar no
Firestore e no Vertex AI (e a spec proíbe chave de conta de serviço em arquivo):

1. **IA:** API do Gemini pelo AI Studio, com chave de API em vez do Vertex. O free tier dava 500 requisições por
   dia no `gemini-3.1-flash-lite` — muito acima do uso de um usuário, que gasta de 3 a 5 por palavra. Porém, no
   free tier o Google usa os dados enviados para treinar seus modelos.
2. **Banco:** SQLite no lugar do Firestore — a alternativa que o [ADR-0003](0003-firestore-como-banco-atras-de-repository.md)
   já registrou como a mais forte.
3. **Export:** arquivo local no lugar do bucket com URL assinada. Falta resolver a entrega: hoje mandamos um link,
   e um arquivo local não é alcançável pelo WhatsApp. A checar: se o WAHA passou a permitir `sendFile` (desde a
   2026.6.1 ele não separa mais Core e Plus), o arquivo vira anexo e o Storage some.

## Decisão

Continuamos na GCP, com a VM `e2-micro` e o IP externo efêmero, e aceitamos o custo de até ~US$ 3,60/mês — hoje
coberto pelos créditos do trial. Nenhuma migração agora.

Em contrapartida, o projeto **não ganha nenhuma dependência nova da GCP**: o `Repository` e o `Armazenamento`
continuam sendo interfaces com mais de uma implementação, e a IA continua atrás do `LLMProvider`
([ADR-0005](0005-llm-atras-de-provider-com-validacao-propria.md)). É isso que mantém as três trocas acima como
trabalho de um marco, e não de uma reescrita.

## Alternativas consideradas

- **Migrar já para máquina em casa** — é o único caminho de custo verdadeiramente zero e o que melhor aproveita o
  fato de o bot não precisar de entrada. Rejeitado **agora** porque a infra da GCP já está provisionada e o deploy
  está a um comando; migrar antes de o bot funcionar uma vez troca um custo conhecido e pequeno por um atraso e por
  três trocas de componente ainda não exercitadas.
- **Migrar já para a Oracle** — resolveria o custo sem tirar o bot da nuvem, mas carrega as mesmas três trocas da
  opção doméstica (é fora da GCP) **mais** o risco de capacidade e de encerramento de conta, sem a vantagem de
  custo zero absoluto de uma máquina que já é sua.
- **Cloud NAT para dispensar o IP externo** — não resolve: custa mais e a spec o proíbe.
- **Desligar a VM quando não estiver em uso** — o WhatsApp exige a sessão viva; desligar derruba o pareamento.

## Consequências

- Fácil: seguir para o M8 hoje, com o custo coberto pelo trial; e decidir depois com o dado real da fatura em vez
  de estimativa.
- Difícil: fica uma decisão em aberto com prazo — ela precisa ser revista **antes do fim dos créditos do trial**,
  não depois de a cobrança começar. A portabilidade só continua barata enquanto ninguém acoplar lógica de negócio
  ao Firestore, ao GCS ou ao Vertex diretamente; qualquer PR que fure uma dessas interfaces encarece a saída.
- A checar quando a decisão for revista: o SKU do IP na fatura real; se o WAHA ganhou `sendFile`; e os limites do
  free tier da API do Gemini, que mudaram várias vezes em 2026.
- **Revisitar se:** os créditos do trial acabarem, a fatura confirmar a cobrança do IP e o valor incomodar, ou
  se aparecer uma máquina doméstica ligada o tempo todo (um Pi ou um mini PC) — que é o cenário em que a opção
  gratuita passa a valer o esforço.
