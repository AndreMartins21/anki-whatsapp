# ADR-0005: IA atrás de um provedor que devolve JSON, com validação e nova tentativa próprias

- **Status:** Aceito
- **Data:** 2026-09-20
- **Fonte:** `spec/spec-inicial.md` seção 6

## Contexto

A spec pede duas implementações intercambiáveis (Gemini no Vertex AI como padrão, Anthropic como
opcional) e funções de negócio (`explain`, `evaluate`, `examples`, `expansions`) que não saibam qual está
em uso. As duas SDKs têm mecanismos próprios de saída estruturada — `response_schema` no Gemini,
*tool use* com `tool_choice` forçado na Anthropic — e a resposta precisa ser validada e, se falhar,
repetida uma vez (temperatura 0.2–0.3). Regras que o schema não expressa (exatamente `n` exemplos,
expansões sem repetir as que o aluno já tem) também precisam de nova tentativa.

## Decisão

- `LLMProvider.gerar(...)` devolve **o JSON como texto**; só isso muda entre provedores.
- A validação Pydantic, a regra extra opcional (`validar`) e a nova tentativa — que reenvia o pedido
  avisando o modelo do que estava errado — vivem numa função comum, `_gerar_validado`, igual para os dois.
- As quatro tarefas ficam em `LLMTutor`, atrás do protocolo `Tutor`, que é o que os fluxos (M4) usam.
  Ele recebe dois modelos: um para explicar/exemplos/expansões e outro, possivelmente maior, para avaliar.
- O texto do usuário vai delimitado por tags e o prompt de sistema o declara como dado, não instrução.
- O cliente Vertex usa `vertexai=True`: funciona em toda versão da SDK (`google-genai>=1.0`); nas
  recentes é o apelido legado de `enterprise=True`.

## Alternativas consideradas

- **Usar `response.parsed` da SDK do Gemini** — pouparia o `model_validate_json`, mas acopla a validação e
  a nova tentativa ao Gemini; a Anthropic teria de reimplementar as duas coisas.
- **Biblioteca de orquestração (`instructor`, LangChain)** — dependência grande para quatro chamadas, e
  esconde exatamente o ponto que queremos controlar (retry com o erro de volta para o modelo).
- **Um `if provider == ...` dentro de cada função de negócio** — espalha o conhecimento dos dois provedores
  por quatro funções e impede testar a lógica com um único fake.

## Consequências

- Fácil: testar `LLMTutor` inteiro (validação, retry, regras extras, escolha de modelo) com um
  `FakeLLMProvider` que só devolve texto; adicionar um terceiro provedor é implementar um método.
- Difícil: o schema enviado ao Gemini (`$defs`, valores padrão, `minItems`) foi escrito sem poder ser
  exercitado contra a API real — o primeiro `make evals` com a API do Vertex ativa é a verificação, e
  qualquer campo que o Gemini recuse deve ser simplificado no schema (a validação local continua valendo).
  Erros de rede/cota do provedor não são repetidos aqui: propagam e o webhook responde com a mensagem de erro.
- Revisitar se: o Gemini rejeitar os schemas atuais de forma que exija schemas separados por provedor, ou se
  um terceiro provedor precisar de mais do que "texto JSON" como contrato.
