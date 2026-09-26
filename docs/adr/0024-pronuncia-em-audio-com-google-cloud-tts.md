# ADR-0024: Pronúncia em áudio sob demanda, com Google Cloud TTS e cache permanente no GCS

- **Status:** Aceito
- **Data:** 2026-09-26

## Contexto

Ouvir a pronúncia de um termo novo é parte de aprendê-lo, e o bot só falava texto (a spec tinha
"áudio" fora do escopo). Restrições e fatos:

- A VM é uma **e2-micro de 1 GB** e já tem ~700 MB reservados (WAHA 400m + bot 300m). Um TTS local
  (Kokoro, Piper) não cabe nela; rodar num serviço à parte (Cloud Run) traria cold start de vários
  segundos, imagem grande e mais infra para manter.
- A maioria dos termos do bot são **expressões e phrasal verbs**, não palavras soltas.
- O Cloud Text-to-Speech tem cota gratuita mensal por tipo de voz (1M de caracteres para Neural2 e
  Chirp 3 HD; 4M para Standard e WaveNet). Um termo ou frase tem dezenas de caracteres.
- O WhatsApp só mostra uma nota de voz se for **OGG/Opus** (doc do WAHA, `POST /api/sendVoice`); o
  Cloud TTS entrega `OGG_OPUS` direto, sem ffmpeg.
- O bucket de exports apaga tudo em 7 dias (ADR-0015), então não serve de cache.

## Decisão

- **Sob demanda, nunca automático.** A opção **1** do menu ("Hear how it sounds 🔊") e o comando
  `/listen N|palavra` mandam um texto curto (o termo e o exemplo) e **duas notas de voz**: o termo
  e a frase de exemplo do card (a frase do bot mais antiga da entrada). A conversa segue onde estava.
- **O menu é renumerado**: 1 ouvir, 2 exemplos, 3 sinônimos, 4 salvar, 5 ignorar (a opção "ignorar"
  do ADR-0021 passa de 4 para 5; o comportamento é o mesmo). O áudio fica no topo porque é o que se faz
  primeiro com um termo novo. O cartão de palavra repetida também oferece o áudio.
- **Google Cloud TTS** (`en-US-Neural2-F`, configurável em `TTS_VOICE`), atrás de uma interface
  `Sintetizador`, autenticado pela conta de serviço da VM (sem chave). Formato `OGG_OPUS`.
- **Cache por hash em um bucket próprio e permanente** (`${PROJECT_ID}-vocabot-audio`, privado, sem
  lifecycle): `audio/<voz>/<sha256 do texto normalizado + voz>.ogg`. É compartilhado entre espaços:
  o mesmo termo é sintetizado uma vez só. O objeto é a fonte da verdade.
- O banco guarda o link (`gs://…`) em `Entry.audio_palavra` e `Entry.audio_exemplo`, só como
  registro: se a voz ou a frase mudar, o hash muda e o áudio novo é gerado sem migração.
- Envio por `Channel.send_voice` (`POST /api/sendVoice`, base64, sem retentativa: reenviar
  duplicaria o áudio). Falha do TTS, do Storage ou do envio vira um aviso curto, nunca derruba a
  conversa. Sem `AUDIO_BUCKET` (ou fora de produção) o bot sobe igual e a pronúncia avisa que falhou.
- Só o **envio** de áudio entra no escopo. Receber áudio do aluno continua recusado.

## Alternativas consideradas

- **Kokoro-82M / Piper (open source, CPU) na VM** — não cabe nos 1 GB. Em Cloud Run, o ganho (voz
  boa, sem custo por caractere) não paga o cold start, a imagem grande, o ffmpeg para Opus e o deploy
  extra, já que a cota gratuita do Cloud TTS cobre o volume. Reavaliar se o custo virar problema.
- **Dicionário com áudio humano (dictionaryapi.dev, Wiktionary/Commons)** — só cobre palavra
  isolada, a licença dos áudios é pouco clara e ainda exigiria um TTS de reserva para as expressões.
- **Enviar o áudio junto do card, sempre** — gasta 2 dos 3 slots de mensagens seguidas
  (`MAX_MENSAGENS_SEGUIDAS`) e sintetiza para termos que o aluno nunca ouviria.
- **Cache no bucket de exports com prefixo próprio** — mistura dado temporário e permanente numa
  regra de lifecycle que vale para o bucket inteiro; um bucket dedicado é mais simples e mais seguro.
- **Guardar só o link do banco e confiar nele** — a URL assinada expira, e o `gs://` ficaria
  velho se a voz mudasse. O hash torna o cache autoexplicativo.

## Consequências

- Nova dependência (`google-cloud-texttospeech`), nova API (`texttospeech.googleapis.com`) e um
  bucket a mais em `infra/setup.sh`. O TTS é cobrado por caractere depois da cota gratuita.
- O primeiro pedido de um termo demora o tempo da síntese (o "digitando…" cobre a espera); os
  seguintes vêm do cache.
- O objeto é lido inteiro do GCS e reenviado em base64, porque o bucket é privado. Serve para áudios
  de poucos segundos.
- Monitorar o consumo de caracteres do TTS no console. Trocar de voz gera um novo conjunto de
  arquivos (o antigo fica no bucket, sem custo relevante).
