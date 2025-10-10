# 🚀 Guia Completo de Deploy APNs no Google Cloud Platform

## 📋 RESUMO

Você vai configurar o APNs no GCP em **4 passos simples**:

1. ✅ Criar secret no Secret Manager
2. ✅ Substituir o cloudbuild.yaml
3. ✅ Fazer deploy
4. ✅ Verificar se funcionou

**Tempo estimado:** 10 minutos

---

## 🔐 PASSO 1: CRIAR SECRET NO SECRET MANAGER

O arquivo `.p8` precisa ser armazenado de forma segura no Google Secret Manager.

### 1.1. Fazer upload do arquivo .p8

```bash
# Navegue até onde está o arquivo (exemplo: Downloads)
cd ~/Downloads

# Crie o secret a partir do arquivo
gcloud secrets create apns-auth-key \
  --project=teste-notificacao-barbearia \
  --replication-policy="automatic" \
  --data-file="AuthKey_UD85TPJ89Y.p8"
```

**Resposta esperada:**
```
Created secret [apns-auth-key].
```

### 1.2. Verificar se foi criado

```bash
gcloud secrets list --project=teste-notificacao-barbearia
```

**Você deve ver:**
```
NAME                          CREATED              REPLICATION_POLICY
apns-auth-key                 2025-XX-XX XX:XX:XX  automatic
firebase-admin-credentials    ...                  automatic
```

### 1.3. Dar permissão ao Cloud Run

```bash
# Obter o número do projeto
PROJECT_NUMBER=$(gcloud projects describe teste-notificacao-barbearia --format="value(projectNumber)")

# Dar permissão de leitura ao Cloud Run
gcloud secrets add-iam-policy-binding apns-auth-key \
  --project=teste-notificacao-barbearia \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

**Resposta esperada:**
```
Updated IAM policy for secret [apns-auth-key].
```

✅ **Passo 1 concluído!** O secret está criado e o Cloud Run tem permissão para acessá-lo.

---

## 📝 PASSO 2: SUBSTITUIR O cloudbuild.yaml

Você tem 2 opções:

### **Opção A: Substituir o arquivo atual (RECOMENDADO)**

```bash
cd /caminho/para/barbearia-backend

# Fazer backup do cloudbuild.yaml atual
cp cloudbuild.yaml cloudbuild-backup.yaml

# Substituir pelo novo
cp cloudbuild-apns.yaml cloudbuild.yaml
```

### **Opção B: Editar manualmente**

Abra o `cloudbuild.yaml` e faça estas 2 mudanças:

#### **Mudança 1: Adicionar o secret APNs**

Encontre esta linha:
```yaml
- '--set-secrets'
- 'FIREBASE_ADMIN_CREDENTIALS=firebase-admin-credentials:latest'
```

Substitua por:
```yaml
- '--set-secrets'
- 'FIREBASE_ADMIN_CREDENTIALS=firebase-admin-credentials:latest,/app/secrets/apns-auth-key.p8=apns-auth-key:latest'
```

#### **Mudança 2: Adicionar variáveis de ambiente APNs**

Encontre esta linha:
```yaml
- '--set-env-vars'
- 'CLOUD_STORAGE_BUCKET_NAME=barbearia-app-fotoss,GCP_PROJECT_ID=teste-notificacao-barbearia,KMS_CRYPTO_KEY_NAME=projects/...'
```

Adicione no final (antes do fechamento das aspas):
```yaml
,APNS_KEY_PATH=/app/secrets/apns-auth-key.p8,APNS_KEY_ID=UD85TPJ89Y,APNS_TEAM_ID=M83XX73UUS,APNS_TOPIC=web.ygg.conciergeanalicegrubert,APNS_USE_SANDBOX=False
```

A linha completa ficará:
```yaml
- '--set-env-vars'
- 'CLOUD_STORAGE_BUCKET_NAME=barbearia-app-fotoss,GCP_PROJECT_ID=teste-notificacao-barbearia,KMS_CRYPTO_KEY_NAME=projects/teste-notificacao-barbearia/locations/southamerica-east1/keyRings/barbearia-app-keys/cryptoKeys/firestore-data-key/cryptoKeyVersions/1,APNS_KEY_PATH=/app/secrets/apns-auth-key.p8,APNS_KEY_ID=UD85TPJ89Y,APNS_TEAM_ID=M83XX73UUS,APNS_TOPIC=web.ygg.conciergeanalicegrubert,APNS_USE_SANDBOX=False'
```

✅ **Passo 2 concluído!** O cloudbuild.yaml está atualizado.

---

## 🚀 PASSO 3: FAZER O DEPLOY

Agora é só fazer o deploy como sempre:

```bash
cd /caminho/para/barbearia-backend

# Deploy via Cloud Build
gcloud builds submit --config cloudbuild.yaml .
```

**O que vai acontecer:**

1. ⏳ **Build da imagem Docker** (1-2 minutos)
   - Instala o `pyapns2` do requirements.txt
   - Copia todos os arquivos Python

2. ⏳ **Push para Artifact Registry** (30 segundos)
   - Envia a imagem para o repositório

3. ⏳ **Deploy no Cloud Run** (1-2 minutos)
   - Monta o secret como arquivo em `/app/secrets/apns-auth-key.p8`
   - Configura as variáveis de ambiente APNs
   - Reinicia o serviço

**Tempo total:** 3-5 minutos

**Mensagem de sucesso:**
```
Deploying container to Cloud Run service [barbearia-backend-service]
✓ Deploying new service... Done.
  ✓ Creating Revision...
  ✓ Routing traffic...
  ✓ Setting IAM Policy...
Done.
Service [barbearia-backend-service] revision [barbearia-backend-service-00XXX-xxx] has been deployed
```

✅ **Passo 3 concluído!** A aplicação está no ar com APNs configurado.

---

## ✅ PASSO 4: VERIFICAR SE FUNCIONOU

### 4.1. Verificar os logs do Cloud Run

```bash
# Ver os logs recentes do serviço
gcloud run services logs read barbearia-backend-service \
  --project=teste-notificacao-barbearia \
  --region=southamerica-east1 \
  --limit=50
```

**Procure por esta linha:**
```
✅ APNs Service inicializado com sucesso (Topic: web.ygg.conciergeanalicegrubert, Sandbox: False)
```

Se você ver isso, **está funcionando!** 🎉

### 4.2. Testar via API (se você adicionou o endpoint de status)

```bash
# Obter a URL do serviço
SERVICE_URL=$(gcloud run services describe barbearia-backend-service \
  --project=teste-notificacao-barbearia \
  --region=southamerica-east1 \
  --format="value(status.url)")

# Testar o endpoint de status (precisa de autenticação)
curl -H "Authorization: Bearer SEU_TOKEN_AQUI" \
  ${SERVICE_URL}/api/apns/status
```

**Resposta esperada:**
```json
{
  "apns_habilitado": true,
  "topic": "web.ygg.conciergeanalicegrubert",
  "sandbox": false,
  "mensagem": "APNs está configurado e pronto para uso!"
}
```

### 4.3. Verificar variáveis de ambiente no Cloud Run

```bash
# Ver todas as variáveis de ambiente configuradas
gcloud run services describe barbearia-backend-service \
  --project=teste-notificacao-barbearia \
  --region=southamerica-east1 \
  --format="value(spec.template.spec.containers[0].env)"
```

**Você deve ver:**
```
APNS_KEY_PATH=/app/secrets/apns-auth-key.p8
APNS_KEY_ID=UD85TPJ89Y
APNS_TEAM_ID=M83XX73UUS
APNS_TOPIC=web.ygg.conciergeanalicegrubert
APNS_USE_SANDBOX=False
...
```

### 4.4. Verificar secrets montados

```bash
# Ver secrets montados
gcloud run services describe barbearia-backend-service \
  --project=teste-notificacao-barbearia \
  --region=southamerica-east1 \
  --format="value(spec.template.spec.volumes)"
```

**Você deve ver:**
```
name=apns-auth-key
secret.secretName=apns-auth-key
secret.items[0].key=latest
secret.items[0].path=apns-auth-key.p8
```

✅ **Passo 4 concluído!** Tudo está funcionando!

---

## 🔍 TROUBLESHOOTING

### ❌ Erro: "Secret not found: apns-auth-key"

**Causa:** O secret não foi criado ou tem nome diferente.

**Solução:**
```bash
# Verificar se o secret existe
gcloud secrets list --project=teste-notificacao-barbearia | grep apns

# Se não existir, criar:
gcloud secrets create apns-auth-key \
  --project=teste-notificacao-barbearia \
  --replication-policy="automatic" \
  --data-file="AuthKey_UD85TPJ89Y.p8"
```

### ❌ Erro: "Permission denied" ao acessar secret

**Causa:** Cloud Run não tem permissão para ler o secret.

**Solução:**
```bash
PROJECT_NUMBER=$(gcloud projects describe teste-notificacao-barbearia --format="value(projectNumber)")

gcloud secrets add-iam-policy-binding apns-auth-key \
  --project=teste-notificacao-barbearia \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

### ❌ Log mostra: "APNs desabilitado"

**Causa:** Variáveis de ambiente não foram configuradas corretamente.

**Solução:** Verifique se as variáveis estão no cloudbuild.yaml:
```bash
# Ver configuração atual
gcloud run services describe barbearia-backend-service \
  --project=teste-notificacao-barbearia \
  --region=southamerica-east1 \
  --format="value(spec.template.spec.containers[0].env)" | grep APNS
```

Se não aparecer nada, o cloudbuild.yaml não foi atualizado corretamente.

### ❌ Erro: "File not found: /app/secrets/apns-auth-key.p8"

**Causa:** O secret não foi montado como arquivo.

**Solução:** Verifique se a linha `--set-secrets` está correta no cloudbuild.yaml:
```yaml
- '--set-secrets'
- 'FIREBASE_ADMIN_CREDENTIALS=firebase-admin-credentials:latest,/app/secrets/apns-auth-key.p8=apns-auth-key:latest'
```

Note o formato: `/app/secrets/apns-auth-key.p8=apns-auth-key:latest`

### ❌ Notificações não chegam no Safari

**Possíveis causas:**
1. Frontend não está registrando tokens APNs
2. Topic errado (deve ser `web.ygg.conciergeanalicegrubert`)
3. Sandbox vs Produção (deve ser `APNS_USE_SANDBOX=False`)
4. Safari versão antiga (precisa 16.4+)

**Solução:** Verifique os logs quando você enviar uma notificação:
```bash
gcloud run services logs read barbearia-backend-service \
  --project=teste-notificacao-barbearia \
  --region=southamerica-east1 \
  --limit=100 | grep -i apns
```

---

## 📊 RESUMO DO QUE FOI CONFIGURADO

| Item | Valor | Onde |
|------|-------|------|
| **Secret Name** | `apns-auth-key` | Secret Manager |
| **Secret Content** | Arquivo `.p8` | Secret Manager |
| **Montado em** | `/app/secrets/apns-auth-key.p8` | Cloud Run Container |
| **APNS_KEY_PATH** | `/app/secrets/apns-auth-key.p8` | Variável de ambiente |
| **APNS_KEY_ID** | `UD85TPJ89Y` | Variável de ambiente |
| **APNS_TEAM_ID** | `M83XX73UUS` | Variável de ambiente |
| **APNS_TOPIC** | `web.ygg.conciergeanalicegrubert` | Variável de ambiente |
| **APNS_USE_SANDBOX** | `False` | Variável de ambiente |

---

## 🔄 FUTURAS ATUALIZAÇÕES

### Para atualizar apenas o código (sem mexer no secret):

```bash
# Deploy normal
gcloud builds submit --config cloudbuild.yaml .
```

### Para atualizar o arquivo .p8 (se expirar):

```bash
# Adicionar nova versão do secret
gcloud secrets versions add apns-auth-key \
  --project=teste-notificacao-barbearia \
  --data-file="NovoAuthKey.p8"

# Fazer deploy novamente (vai pegar a versão "latest" automaticamente)
gcloud builds submit --config cloudbuild.yaml .
```

### Para trocar de Sandbox para Produção (ou vice-versa):

Edite o `cloudbuild.yaml` e troque:
```yaml
APNS_USE_SANDBOX=False  →  APNS_USE_SANDBOX=True
```

Depois faça deploy:
```bash
gcloud builds submit --config cloudbuild.yaml .
```

---

## ✅ CHECKLIST FINAL

### Antes do deploy:
- [x] Código APNs implementado no backend
- [ ] Arquivo `AuthKey_UD85TPJ89Y.p8` disponível localmente
- [ ] Secret `apns-auth-key` criado no Secret Manager
- [ ] Permissões configuradas para o Cloud Run
- [ ] `cloudbuild.yaml` atualizado com secrets e variáveis APNs

### Depois do deploy:
- [ ] Build executado com sucesso
- [ ] Deploy no Cloud Run concluído
- [ ] Log mostra "APNs Service inicializado com sucesso"
- [ ] Variáveis de ambiente corretas
- [ ] Secret montado como arquivo

### Próximos passos:
- [ ] Implementar frontend (Flutter Web + JavaScript)
- [ ] Testar registro de token Safari
- [ ] Testar envio de notificação para Safari
- [ ] Testar em produção com usuários reais

---

## 🎯 COMANDOS RÁPIDOS (COPIAR E COLAR)

Se você só quer copiar e colar tudo de uma vez:

```bash
# 1. Criar secret
cd ~/Downloads
gcloud secrets create apns-auth-key \
  --project=teste-notificacao-barbearia \
  --replication-policy="automatic" \
  --data-file="AuthKey_UD85TPJ89Y.p8"

# 2. Dar permissão
PROJECT_NUMBER=$(gcloud projects describe teste-notificacao-barbearia --format="value(projectNumber)")
gcloud secrets add-iam-policy-binding apns-auth-key \
  --project=teste-notificacao-barbearia \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

# 3. Voltar para o backend e fazer backup
cd /caminho/para/barbearia-backend
cp cloudbuild.yaml cloudbuild-backup.yaml

# 4. Substituir cloudbuild.yaml
cp cloudbuild-apns.yaml cloudbuild.yaml

# 5. Deploy!
gcloud builds submit --config cloudbuild.yaml .

# 6. Verificar logs
gcloud run services logs read barbearia-backend-service \
  --project=teste-notificacao-barbearia \
  --region=southamerica-east1 \
  --limit=50 | grep -i apns
```

---

## 🎉 PRONTO!

Depois de executar esses comandos, seu backend estará **100% operacional** no GCP com suporte a:

- ✅ **FCM** (Android/Chrome/Edge) - continua funcionando
- ✅ **APNs** (Safari/iOS) - agora também funciona!

**Próximo passo:** Implementar o frontend para registrar tokens Safari. 🚀

---

## 📞 PRECISA DE AJUDA?

Se algo der errado:

1. Verifique os logs: `gcloud run services logs read barbearia-backend-service`
2. Verifique os secrets: `gcloud secrets list --project=teste-notificacao-barbearia`
3. Verifique as variáveis: `gcloud run services describe barbearia-backend-service`

Qualquer erro, me avise! 🛠️
