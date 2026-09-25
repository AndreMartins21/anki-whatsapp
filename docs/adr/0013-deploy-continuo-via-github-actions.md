# ADR-0013: Deploy contínuo via GitHub Actions, autenticado por Workload Identity Federation

- **Status:** Aceito
- **Data:** 2026-09-23
- **Fonte:** `spec/spec-inicial.md` seção 10, ADR-0007 (menor privilégio e IAP), skill `gcp-best-practices`

## Contexto

O deploy hoje (`infra/deploy.sh`) é manual: alguém roda o script no próprio computador, autenticado
como Owner, empacota o código, copia para a VM via IAP e sobe o compose. Isso funciona com um único
operador, mas cada deploy depende de lembrar de rodar o script, e a `main` não tem nenhuma barreira
antes do código chegar em produção — dá para commitar direto nela.

O repositório é **público** no GitHub. Isso não muda a decisão de automatizar, mas muda o desenho:
`pull_request` de um fork roda com um `GITHUB_TOKEN` restrito e sem acesso a segredos do repositório
(comportamento padrão do GitHub para repositório público); mesmo assim, nenhum segredo ou dado do
usuário pode aparecer em log de Action, porque logs de repositório público são visíveis a qualquer
pessoa.

## Decisão

- **Branch protection na `main`:** exige Pull Request (sem push direto) e os três checks do
  `ci.yml` (`checks`, `test`, `compose`) como obrigatórios antes do merge.
- **Deploy automático e sem aprovação manual** roda como um quarto job (`deploy`) no mesmo
  `ci.yml`, disparado só em `push` para `main` (ou seja, só depois do merge de um PR já verde) e só
  depois que `checks`, `test` e `compose` passarem (`needs:`). Decisão do usuário: sem gate de
  aprovação humana entre o merge e o deploy — o CI já é a barreira de qualidade.
- **Autenticação por Workload Identity Federation (WIF)**, sem chave de conta de serviço em
  arquivo — consistente com ADR-0007. Um pool + provider OIDC confia no emissor de tokens do GitHub
  Actions (`token.actions.githubusercontent.com`) e a *attribute condition* restringe o token a
  `assertion.repository == 'AndreMartins21/anki-whatsapp' && assertion.ref == 'refs/heads/main'` —
  nenhum fork, nenhuma outra branch e nenhum outro repositório consegue um token, mesmo que copie o
  workflow.
- **Conta de serviço dedicada `vocabot-deploy`**, diferente da `vocabot-vm` (que é a identidade de
  execução do bot na VM). Recebe **no nível da instância** só `roles/compute.osAdminLogin` (logar
  via OS Login com sudo). `roles/iap.tunnelResourceAccessor` e `roles/compute.viewer` só puderam
  ser concedidos **no projeto**, por dois motivos técnicos confirmados tentando (não por escolha):
  o recurso "túnel IAP" de uma instância não tem binding por
  `gcloud compute instances add-iam-policy-binding` (a API rejeita com "role not supported for this
  resource"; o caminho documentado pela Google por instância é uma chamada crua à API REST do IAP,
  mais frágil num script idempotente do que um `gcloud` padrão); e `gcloud compute scp`/`ssh` chamam
  `compute.projects.get` antes de conectar, uma permissão que só existe no escopo do projeto — um
  binding de `compute.viewer` só na instância falha o deploy real com "Required
  compute.projects.get permission" (foi o que aconteceu no primeiro deploy automático). Como este
  projeto nunca tem mais de uma VM (spec 10.8), os dois bindings no projeto já ficam, na prática,
  restritos à `vocabot-vm`. Recebe também `roles/iam.serviceAccountUser` **só sobre a `vocabot-vm`**:
  como a VM roda como essa conta, o SSH falha com `iam.serviceAccounts.actAs` sem esse papel (foi o
  segundo erro do primeiro deploy automático). Não recebe acesso direto a Secret Manager,
  Firestore, Storage ou Vertex AI, e quem lê os segredos e renderiza o `.env` continua sendo a
  própria VM (nada muda em `infra/deploy.sh`). **Mas o alcance real é maior que essa lista:**
  `osAdminLogin` dá root na VM e `serviceAccountUser` permite agir como `vocabot-vm`, então quem
  controlar o job `deploy` alcança tudo que a `vocabot-vm` alcança. A defesa é a attribute
  condition do provider (só este repo, só a `main`) e a branch protection — por isso a proteção da
  `main` não é opcional.
- **Segredos de verdade (PII) em GitHub Secrets, não em Variables:** `ALLOWED_NUMBER` e
  `BOT_NUMBER` são números de telefone reais — vão como *Secrets* do repositório (mascarados em log
  automaticamente) mesmo não sendo credencial de acesso. O resto (`GCP_PROJECT_ID`,
  `GCP_WIF_PROVIDER`, `LLM_PROVIDER`, `GEMINI_MODEL`, `GEMINI_MODEL_EVAL`, `USER_LEVEL`, `TIMEZONE`)
  são *Variables*, sem necessidade de mascaramento.

## Alternativas consideradas

- **Chave de conta de serviço (`.json`) em GitHub Secret** — mais simples de configurar, mas é uma
  credencial de longa duração fora do padrão ADC que já usamos em todo o resto da infra (ADR-0007);
  vaza por engano com mais facilidade do que um token de vida curta trocado por OIDC.
- **Gate de aprovação manual (GitHub Environment com required reviewer)** — reduz o raio de
  explosão de um merge ruim, mas o usuário preferiu manter o deploy totalmente automático e confiar
  no CI como barreira; revisitar se algum merge quebrar produção sem o CI pegar.
- **Workflow separado disparado por `workflow_run`** — evita duplicar o trigger `push: main`, mas
  cria uma dependência indireta entre dois arquivos de workflow, mais difícil de ler; um job
  `deploy` com `needs` no mesmo `ci.yml` é mais simples e a ordem fica explícita.
- **`vocabot-deploy` com papéis no projeto em vez de na instância** — mais simples de conceder, mas
  dá acesso à VM (e a qualquer VM futura) além da necessária; o custo de escopar por instância é uma
  flag a mais no `gcloud`.

## Consequências

- Fácil: mergear um PR já é publicar; nenhum passo manual sobra além de escrever o PR e revisar.
- Difícil: reverter um deploy ruim exige `git revert` + novo merge (não há passo manual para
  segurar); rotacionar `ALLOWED_NUMBER`/`BOT_NUMBER` no GitHub exige atualizar o Secret e re-rodar o
  workflow.
- Monitorar: `infra/smoke_test.sh` deveria rodar como último passo do job `deploy` para o workflow
  falhar (e ficar visível) se o bot não subir — sem isso, um deploy quebrado só aparece quando
  alguém tenta usar o bot. O smoke test **espera** o bot e o WAHA (até 3 min cada): sem isso, todo
  deploy que recria o WAHA falhava por uma corrida (o GOWS leva mais de 10 s para subir e reinicia
  algumas vezes), com o bot saudável e o workflow vermelho à toa (visto no deploy do M17).
- Revisitar se: aparecer um segundo operador (aí um gate de aprovação manual volta a fazer
  sentido) ou se a VM virar mais de uma instância (o binding por instância vira lista).
