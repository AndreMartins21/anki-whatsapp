# ADR-0001: Stack do MVP (WAHA + Gemini no Vertex AI + VM e2-micro)

- **Status:** Aceito
- **Data:** 2026-09-20
- **Fonte:** decisões fixadas em `spec/spec-inicial.md` (seções 2 e 10.8)

## Contexto

Bot pessoal de WhatsApp, um único usuário, orçamento praticamente zero (nível gratuito do GCP mais
créditos de trial). O número do bot é um chip comum com WhatsApp Business, não uma conta de
WhatsApp Business Platform aprovada pela Meta.

## Decisão

- **Canal:** WAHA Core self-hosted (engine GOWS), conectado como aparelho vinculado — não a Cloud API
  oficial da Meta.
- **IA:** Gemini no Vertex AI via SDK `google-genai` (`vertexai=True`, `location=global`), autenticado
  pela conta de serviço da VM, sem chave de API. A família Gemini 2.5 está fora (aposentadoria em
  outubro/2026). `LLM_PROVIDER=anthropic` fica como alternativa opcional.
- **Hospedagem:** uma VM Compute Engine `e2-micro` em `us-central1`, Debian 12, disco standard de
  30 GB, Docker Compose com os serviços `waha` e `bot`.
- **Dados:** Firestore nativo; exportações em bucket privado do Cloud Storage com URL assinada V4.
- **Acesso:** SSH só via IAP; nenhuma porta pública além disso.

## Alternativas consideradas

- **Cloud API oficial da Meta** — exige número aprovado, processo de verificação e custo por conversa;
  desproporcional para um usuário.
- **Engine WEBJS do WAHA** — roda Chromium e não cabe em 1 GB de RAM.
- **Claude no Vertex AI** — modelos de parceiros não são cobertos pelos créditos de trial.
- **Cloud Run** — sem processo de longa duração para manter a sessão do WhatsApp viva.

## Consequências

- Só 1 GB de RAM: swap de 2 GB obrigatório, `mem_limit` nos containers e nada de serviços extras.
- Conta não oficial implica risco de bloqueio → comportamento "humano" (seção 5.6 da spec) não é
  enfeite, é requisito.
- A dependência do WAHA fica isolada atrás da interface `Channel`, para permitir trocar o canal
  depois sem reescrever a lógica de negócio.
- Revisitar se: o volume crescer, aparecer um segundo usuário, ou o WAHA Core quebrar com uma
  atualização do WhatsApp.
