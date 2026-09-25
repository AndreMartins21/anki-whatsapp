# ADR-0022: Retentativa do Gemini no próprio SDK e erro do provedor tratado como `LLMError`

- **Status:** Aceito
- **Data:** 2026-09-25

## Contexto

Em 2026-09-25, entre 10:26 e 11:05 (BRT), cinco mensagens receberam "⚠️ Something went wrong on my
end". Os logs mostram o mesmo padrão nas cinco: `429 RESOURCE_EXHAUSTED` do Vertex AI
(`gemini-3.1-flash-lite`, endpoint `global`) na explicação da palavra. É a capacidade compartilhada
do modelo apertando; o volume do projeto é pequeno demais para ser cota própria.

Duas falhas nossas transformaram um erro transitório num erro visível:

- o cliente `google-genai` não estava configurado para retentar: cada 429 falhava na primeira
  chamada (uma única requisição por falha nos logs);
- `errors.APIError` não era `LLMError`, então caía no aviso genérico do fim do webhook em vez do
  "I couldn't reach the AI right now" pensado para falha de IA (ADR-0005).

## Decisão

- O cliente Vertex é criado com `HttpRetryOptions`: 4 tentativas, espera de 1 s, 2 s e 4 s (teto
  de 8 s, com jitter) para os status 408, 429, 500, 502, 503 e 504.
- `VertexGeminiProvider.gerar` converte `genai_errors.APIError` e `httpx.HTTPError` em `LLMError`,
  com só o código e o status na mensagem (o corpo da resposta não vai para o log nem para o aluno).

## Alternativas consideradas

- **Laço de retentativa próprio em `_gerar_validado`** — duplicaria o que o SDK já faz, e a nova
  tentativa de lá é para resposta inválida (validação), um motivo diferente.
- **Trocar de modelo ou de região no 429** — mais complexo e custoso, sem evidência de que seja
  preciso; revisitar se o 429 persistir mesmo com a retentativa.
- **Pedir aumento de cota** — não se aplica a capacidade compartilhada dinâmica.
- **Não fazer nada** — o aluno continuaria vendo erro em algo que costuma passar em segundos.

## Consequências

- Uma resposta lenta pode levar alguns segundos a mais no pior caso (até ~7 s de espera somados);
  o indicador "digitando" já cobre a chamada.
- O que persistir depois das 4 tentativas chega ao aluno como "I couldn't reach the AI", com a
  sessão mantida, e no log como `falha da IA` (aviso), não como erro inesperado.
- Se o 429 continuar frequente, medir e considerar modelo de reserva ou throughput provisionado.
