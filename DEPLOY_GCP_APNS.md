# 🚀 Deploy APNs no Google Cloud Platform (GCP)

Guia completo para configurar e fazer deploy do backend com suporte a APNs no Google Cloud Run.

---

## 📋 O QUE VOCÊ PRECISA

✅ Arquivo `AuthKey_UD85TPJ89Y.p8` (você já tem)
✅ Projeto GCP: `teste-notificacao-barbearia`
✅ Secret Manager habilitado (você já usa para Firebase)
✅ Cloud Build configurado (você já tem o `cloudbuild.yaml`)

---

## 🔐 PASSO 1: CRIAR SECRET NO SECRET MANAGER

Você precisa armazenar o arquivo `.p8` de forma segura no Google Secret Manager.

### 1.1. Fazer upload do arquivo .p8 como secret

```bash
# Navegue até a pasta onde está o arquivo .p8
cd ~/Downloads  # ou onde você salvou o arquivo

# Crie o secret a partir do arquivo
gcloud secrets create apns-auth-key \
  --project=teste-notificacao-barbearia \
  --replication-policy="automatic" \
  --data-file="AuthKey_UD85TPJ89Y.p8"
```

**Explicação:**
- Nome do secret: `apns-auth-key`
- Conteúdo: O arquivo `.p8` completo
- Replicação automática: GCP gerencia onde armazenar

### 1.2. Verificar se o secret foi criado

```bash
# Lista todos os secrets
gcloud secrets list --project=teste-notificacao-barbearia

# Você deve ver:
# NAME                          CREATED              REPLICATION_POLICY  LOCATIONS
# apns-auth-key                 2025-XX-XX XX:XX:XX  automatic           -
# firebase-admin-credentials    ...                  automatic           -
```

### 1.3. Dar permissão ao Cloud Run para acessar o secret

```bash
# Obtenha o número do projeto
PROJECT_NUMBER=$(gcloud projects describe teste-notificacao-barbearia --format="value(projectNumber)")

# Dê permissão para o Cloud Run acessar o secret
gcloud secrets add-iam-policy-binding apns-auth-key \
  --project=teste-notificacao-barbearia \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

---

## 📝 PASSO 2: ATUALIZAR O cloudbuild.yaml

Agora você precisa montar o secret como um arquivo no Cloud Run e configurar as variáveis de ambiente.

### 2.1. Arquivo cloudbuild.yaml atualizado

Abra o `cloudbuild.yaml` e modifique o passo 3 (deploy do Cloud Run):

```yaml
steps:
  # 1. Constrói a imagem Docker
- name: 'gcr.io/cloud-builders/docker'
  args:
    - 'build'
    - '--no-cache'
    - '-t'
    - 'southamerica-east1-docker.pkg.dev/teste-notificacao-barbearia/barbearia-repo/barbearia-app:latest'
    - '.'

  # 2. Envia a imagem para o Artifact Registry
- name: 'gcr.io/cloud-builders/docker'
  args:
    - 'push'
    - 'southamerica-east1-docker.pkg.dev/teste-notificacao-barbearia/barbearia-repo/barbearia-app:latest'

  # 3. Faz o deploy da nova imagem no Google Cloud Run
- name: 'gcr.io/google.com/cloudsdktool/cloud-sdk'
  entrypoint: 'gcloud'
  args:
    - 'run'
    - 'deploy'
    - 'barbearia-backend-service'
    - '--image'
    - 'southamerica-east1-docker.pkg.dev/teste-notificacao-barbearia/barbearia-repo/barbearia-app:latest'
    - '--platform'
    - 'managed'
    - '--region'
    - 'southamerica-east1'
    - '--allow-unauthenticated'
    # ========== SECRETS (Firebase + APNs) ==========
    - '--set-secrets'
    - 'FIREBASE_ADMIN_CREDENTIALS=firebase-admin-credentials:latest,/app/secrets/apns-auth-key.p8=apns-auth-key:latest'
    # ========== VARIÁVEIS DE AMBIENTE ==========
    - '--set-env-vars'
    - 'CLOUD_STORAGE_BUCKET_NAME=barbearia-app-fotoss,GCP_PROJECT_ID=teste-notificacao-barbearia,KMS_CRYPTO_KEY_NAME=projects/teste-notificacao-barbearia/locations/southamerica-east1/keyRings/barbearia-app-keys/cryptoKeys/firestore-data-key/cryptoKeyVersions/1,APNS_KEY_PATH=/app/secrets/apns-auth-key.p8,APNS_KEY_ID=UD85TPJ89Y,APNS_TEAM_ID=M83XX73UUS,APNS_TOPIC=web.ygg.conciergeanalicegrubert,APNS_USE_SANDBOX=False'

# Define a imagem que foi construída
images:
  - 'southamerica-east1-docker.pkg.dev/teste-notificacao-barbearia/barbearia-repo/barbearia-app:latest'

# Adiciona a configuração de logging
options:
  logging: CLOUD_LOGGING_ONLY
```

### 2.2. O que mudou?

#### **Secrets montados:**

```yaml
--set-secrets
- 'FIREBASE_ADMIN_CREDENTIALS=firebase-admin-credentials:latest,/app/secrets/apns-auth-key.p8=apns-auth-key:latest'
```

**Antes:** Só tinha Firebase
**Depois:** Firebase + APNs

O secret `apns-auth-key` será montado como um **arquivo** em `/app/secrets/apns-auth-key.p8`

#### **Variáveis de ambiente adicionadas:**

```yaml
--set-env-vars
- '...,APNS_KEY_PATH=/app/secrets/apns-auth-key.p8,APNS_KEY_ID=UD85TPJ89Y,APNS_TEAM_ID=M83XX73UUS,APNS_TOPIC=web.ygg.conciergeanalicegrubert,APNS_USE_SANDBOX=False'
```

**Novas variáveis:**
- `APNS_KEY_PATH`: Caminho para o arquivo .p8 montado
- `APNS_KEY_ID`: UD85TPJ89Y
- `APNS_TEAM_ID`: M83XX73UUS
- `APNS_TOPIC`: web.ygg.conciergeanalicegrubert
- `APNS_USE_SANDBOX`: False (produção)

---

## 📄 PASSO 3: ATUALIZAR O cloudbuild.yaml (ARQUIVO COMPLETO)

Vou criar o arquivo atualizado para você:

