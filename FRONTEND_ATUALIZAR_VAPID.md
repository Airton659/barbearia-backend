# 🔧 AÇÃO NECESSÁRIA NO FRONTEND - Atualizar VAPID

## 🎯 Resumo
As chaves VAPID foram regeneradas no backend para corrigir um bug de formato. O frontend precisa **buscar a nova chave pública** do backend e **registrar uma nova subscription**.

---

## ❌ Problema que estava acontecendo

As notificações VAPID não estavam chegando porque a chave privada estava em um formato incompatível com a biblioteca `pywebpush`.

**Sintomas:**
- ✅ Contador de notificações funcionava
- ✅ Notificação aparecia no app
- ❌ Notificação visual não aparecia na barra do sistema

**Erro nos logs do backend:**
```
❌ Erro Web Push: Could not deserialize key data
```

---

## ✅ Solução Aplicada

Regeneramos as chaves VAPID no formato correto (DER base64url) e fizemos deploy do backend.

---

## 📋 O QUE O FRONTEND PRECISA FAZER

### Opção 1: Se a chave está sendo buscada dinamicamente (RECOMENDADO)

Se você já está usando o endpoint `/vapid-public-key` para buscar a chave, **NÃO PRECISA ALTERAR CÓDIGO**.

**Basta:**
1. Recarregar o app (Ctrl+Shift+R ou Cmd+Shift+R)
2. Fazer logout e login novamente
3. Isso vai buscar a nova chave e registrar nova subscription automaticamente

### Opção 2: Se a chave está hardcoded no código

Se você colocou a chave VAPID pública diretamente no código do frontend, **SUBSTITUA** pela nova chave:

**❌ Chave antiga (NÃO FUNCIONA MAIS):**
```
BPFOyeJzmbD4KpyecEx9WhPRLHnsshBos9ZxtldEN7TRTsVejMYnbfgHB0hMRqf-ZbkMKYAjIu_gL70Fosjzsjo
```

**✅ Nova chave (USE ESSA):**
```
BIquyspknpYhUmUPKPL3pCIa-uzz83BhNBa6P3RagE2iU0YCXx6GEZolLOISgAdmpwSiNcdk9UhldFrB5QnirbQ
```

---

## 🧪 Como Verificar se Está Funcionando

### 1. Verificar se o frontend pegou a nova chave

Abra o console do navegador (F12) e rode:

```javascript
fetch('https://barbearia-backend-service-862082955632.southamerica-east1.run.app/vapid-public-key')
  .then(r => r.json())
  .then(d => {
    console.log('Chave VAPID do backend:', d.publicKey)
    console.log('Tamanho:', d.publicKey.length, 'caracteres')
  })
```

**Resultado esperado:**
```
Chave VAPID do backend: BIquyspknpYhUmUPKPL3pCIa-uzz83BhNBa6P3RagE2iU0YCXx6GEZolLOISgAdmpwSiNcdk9UhldFrB5QnirbQ
Tamanho: 87 caracteres
```

### 2. Verificar se a subscription foi registrada

Depois de fazer login, verifique no console se apareceu:

```
[VAPID] ✅ Web Push configurado com sucesso!
```

### 3. Testar notificação de exame

**Teste rápido (15-20 minutos):**
1. Criar um exame para **daqui 1h e 16 minutos**
   - Exemplo: se agora são 15:30, marque para 16:46
2. Aguardar até o próximo ciclo de 15 minutos
3. Notificação deve chegar **visualmente na barra** (não só no app)

**Por que 1h16min?**
- Sistema envia 1h antes do exame
- Se exame é 16:46, lembrete = 15:46
- Cron roda às: 15:45, 16:00, 16:15...
- No ciclo de 16:00, ele detecta que 15:46 está na janela (15:45-16:00) e envia

---

## 🔍 Verificar no Firestore (Opcional)

Após fazer login, verifique se o campo `webpush_subscription_exames` foi criado/atualizado no documento do usuário:

```
usuarios/{seu_usuario_id}/webpush_subscription_exames
```

Deve conter:
```json
{
  "endpoint": "https://fcm.googleapis.com/...",
  "keys": {
    "p256dh": "...",
    "auth": "..."
  },
  "created_at": "timestamp"
}
```

---

## ⚠️ Importante

- **Todas as subscriptions antigas** com a chave antiga **NÃO VÃO MAIS FUNCIONAR**
- **Todos os usuários** precisam fazer logout/login ou recarregar o app para registrar nova subscription
- Isso é **normal** quando regeneramos chaves VAPID

---

## 📞 Suporte

Se após seguir esses passos a notificação visual ainda não chegar:

1. Verifique os logs do backend no horário que deveria enviar
2. Procure por: `✅ LEMBRETE_EXAME enviado via Web Push`
3. Ou por erros: `❌ Erro Web Push`

---

## 🎉 Status

- ✅ Backend deployado com novas chaves
- ✅ Endpoint `/vapid-public-key` retornando nova chave
- ⏳ Frontend precisa buscar nova chave e registrar nova subscription
- ⏳ Aguardando teste completo de notificação
