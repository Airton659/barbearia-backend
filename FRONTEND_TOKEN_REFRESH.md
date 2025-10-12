# 🔧 SISTEMA HÍBRIDO VAPID + FCM COM TOKEN REFRESH

## 🎯 O que mudou

O backend agora implementa um **sistema híbrido com retry automático** para notificações agendadas:

1. **Tenta VAPID** (Web Push)
2. Se falhar (erro 403/410) → **Remove subscription inválida**
3. **Tenta FCM** como fallback
4. Se FCM funcionar → Notificação é entregue ✅

### Notificações afetadas:
- ✅ LEMBRETE_EXAME (1h antes do exame)
- ✅ TAREFA_ATRASADA (tarefas não concluídas no prazo)
- ✅ LEMBRETE_AGENDADO (notificações manuais agendadas)

---

## 🚨 AÇÃO OBRIGATÓRIA NO FRONTEND

Para que o sistema funcione, o frontend **PRECISA** atualizar os tokens toda vez que o usuário abre o app ou faz login.

### Por quê?

**Problema:**
- Usuário cria exame para daqui 15 dias
- Atualiza navegador 10x nos próximos 15 dias
- Tokens FCM/VAPID mudam
- Firestore ainda tem tokens antigos
- Notificação falha ❌

**Solução:**
- Toda vez que usuário abre app → Pega tokens atuais
- Envia para backend atualizar Firestore
- Quando chegar hora de enviar → Backend usa tokens atuais ✅

---

## 📝 Implementação no Frontend

### 1. Atualizar Token FCM no Login/Abertura

Adicione isso no **onAuthStateChanged** ou **initState** do app:

```javascript
// auth_service.js ou equivalente
async function atualizarTokensFCM(userId) {
  try {
    // Pegar token FCM atual
    const messaging = firebase.messaging();
    const fcmToken = await messaging.getToken({
      vapidKey: 'SUA_CHAVE_VAPID_PUBLICA'
    });

    console.log('[TOKEN-REFRESH] Token FCM obtido:', fcmToken.substring(0, 20) + '...');

    // Enviar para backend atualizar
    const response = await fetch(`${API_URL}/usuarios/${userId}/fcm-token`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${await getAuthToken()}`
      },
      body: JSON.stringify({ token: fcmToken })
    });

    if (response.ok) {
      console.log('[TOKEN-REFRESH] ✅ Token FCM atualizado no backend');
    } else {
      console.error('[TOKEN-REFRESH] ❌ Erro ao atualizar token FCM:', await response.text());
    }
  } catch (error) {
    console.error('[TOKEN-REFRESH] ❌ Erro ao obter/atualizar token FCM:', error);
  }
}
```

### 2. Atualizar Subscription VAPID no Login/Abertura

```javascript
async function atualizarSubscriptionVAPID(userId) {
  try {
    // Registrar Service Worker se ainda não foi
    const registration = await navigator.serviceWorker.ready;

    // Obter chave pública do backend
    const vapidResponse = await fetch(`${API_URL}/vapid-public-key`);
    const { publicKey } = await vapidResponse.json();

    // Criar/atualizar subscription
    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(publicKey)
    });

    console.log('[VAPID-REFRESH] Subscription criada/atualizada');

    // Enviar para backend
    const response = await fetch(`${API_URL}/usuarios/${userId}/webpush-subscription`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${await getAuthToken()}`
      },
      body: JSON.stringify({
        endpoint: subscription.endpoint,
        keys: {
          p256dh: arrayBufferToBase64(subscription.getKey('p256dh')),
          auth: arrayBufferToBase64(subscription.getKey('auth'))
        }
      })
    });

    if (response.ok) {
      console.log('[VAPID-REFRESH] ✅ Subscription VAPID atualizada no backend');
    } else {
      console.error('[VAPID-REFRESH] ❌ Erro ao atualizar subscription:', await response.text());
    }
  } catch (error) {
    console.error('[VAPID-REFRESH] ❌ Erro ao atualizar subscription VAPID:', error);
  }
}

// Helper functions
function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - base64String.length % 4) % 4);
  const base64 = (base64String + padding)
    .replace(/\-/g, '+')
    .replace(/_/g, '/');
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

function arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return window.btoa(binary);
}
```

### 3. Chamar Funções no Momento Certo

```javascript
// No login ou quando app abre
firebase.auth().onAuthStateChanged(async (user) => {
  if (user) {
    console.log('[AUTH] Usuário logado, atualizando tokens...');

    // Buscar ID do usuário no Firestore
    const userDoc = await db.collection('usuarios')
      .where('firebase_uid', '==', user.uid)
      .limit(1)
      .get();

    if (!userDoc.empty) {
      const userId = userDoc.docs[0].id;

      // Atualizar tokens em paralelo
      await Promise.all([
        atualizarTokensFCM(userId),
        atualizarSubscriptionVAPID(userId)
      ]);

      console.log('[AUTH] ✅ Tokens atualizados com sucesso');
    }
  }
});
```

---

## 🔧 Endpoint Necessário no Backend

Precisa criar este endpoint (se ainda não existe):

```python
@app.post("/usuarios/{usuario_id}/fcm-token", tags=["Notificações"])
def atualizar_fcm_token(
    usuario_id: str,
    token_data: dict,
    db: firestore.client = Depends(get_db)
):
    """
    Atualiza o token FCM do usuário.
    Chamado toda vez que usuário abre app ou faz login.
    """
    try:
        token = token_data.get('token')
        if not token:
            raise HTTPException(status_code=400, detail="Token não fornecido")

        usuario_ref = db.collection('usuarios').document(usuario_id)
        usuario_doc = usuario_ref.get()

        if not usuario_doc.exists:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")

        # Adicionar token se não existir, evitar duplicatas
        usuario_data = usuario_doc.to_dict()
        fcm_tokens = usuario_data.get('fcm_tokens', [])

        if token not in fcm_tokens:
            fcm_tokens.append(token)
            # Manter apenas os 3 tokens mais recentes
            fcm_tokens = fcm_tokens[-3:]

            usuario_ref.update({
                'fcm_tokens': fcm_tokens,
                'last_token_update': firestore.SERVER_TIMESTAMP
            })
            logger.info(f"✅ Token FCM atualizado para usuário {usuario_id}")

        return {"status": "success", "message": "Token atualizado"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao atualizar token FCM: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

---

## ✅ Como Testar

### Teste 1: Verificar se tokens estão sendo atualizados

1. Abra o console do navegador (F12)
2. Faça login no app
3. Procure logs:
   ```
   [TOKEN-REFRESH] ✅ Token FCM atualizado no backend
   [VAPID-REFRESH] ✅ Subscription VAPID atualizada no backend
   ```

### Teste 2: Criar exame e fazer logout/login

1. Crie um exame para daqui 1h30min
2. Faça logout
3. Faça login novamente
4. Verifique no Firestore se `fcm_tokens` e `webpush_subscription_exames` foram atualizados
5. Aguarde 1h para ver se notificação chega

### Teste 3: Verificar fallback FCM

1. Crie exame para daqui 1h30min
2. Limpe subscription VAPID do Firestore manualmente
3. Aguarde 1h
4. Notificação deve chegar via FCM (verifique logs do backend)

---

## 📊 Como o Sistema Funciona

```
┌─────────────────────────────────────────────────────────┐
│ FRONTEND: Usuário abre app                              │
└────────────────┬────────────────────────────────────────┘
                 │
                 ├──> Pega token FCM atual
                 ├──> Envia para backend via POST /fcm-token
                 │
                 ├──> Pega chave VAPID pública
                 ├──> Cria subscription VAPID
                 └──> Envia para backend via POST /webpush-subscription

┌─────────────────────────────────────────────────────────┐
│ BACKEND: Salva tokens no Firestore                      │
└────────────────┬────────────────────────────────────────┘
                 │
                 │  (15 dias depois...)
                 │
┌────────────────▼────────────────────────────────────────┐
│ BACKEND: Cron roda (hora de enviar lembrete)            │
└────────────────┬────────────────────────────────────────┘
                 │
                 ├──> 1. Tenta VAPID
                 │       ├─ Sucesso? ✅ FIM
                 │       └─ Erro 403/410? Remove subscription
                 │
                 └──> 2. Tenta FCM (fallback)
                         ├─ Sucesso? ✅ FIM
                         └─ Falha? ❌ Registra erro
```

---

## 🎯 Benefícios

- ✅ **Confiabilidade**: Mesmo se VAPID falhar, FCM tenta entregar
- ✅ **Auto-correção**: Subscriptions inválidas são removidas automaticamente
- ✅ **Tokens sempre atuais**: Frontend atualiza a cada login/abertura
- ✅ **Zero configuração manual**: Tudo automático

---

## ⚠️ Importante

- **Não** remova o sistema VAPID - ele é a primeira tentativa (mais confiável quando funciona)
- **Não** remova FCM - ele é o fallback essencial
- **Sempre** atualize tokens no login/abertura do app
- **Monitore** os logs do backend para ver qual método está sendo usado

---

## 🔍 Monitoramento (Logs do Backend)

Procure por estes logs para entender o que está acontecendo:

### ✅ Sucesso VAPID:
```
✅ LEMBRETE_EXAME enviado via VAPID para 2PHHl9t74ltZ8GvqaLKs
```

### ⚠️ Falha VAPID + Sucesso FCM:
```
⚠️ Falha VAPID para 2PHHl9t74ltZ8GvqaLKs: Push failed: 403 Forbidden, tentando FCM...
⚠️ Subscription VAPID inválida/expirada, removendo...
✅ LEMBRETE_EXAME enviado via FCM para 2PHHl9t74ltZ8GvqaLKs
```

### ❌ Falha total:
```
⚠️ Falha VAPID para 2PHHl9t74ltZ8GvqaLKs: ...
⚠️ Falha FCM token eY0Xd-UXAZ... : ...
❌ FALHA TOTAL: Não foi possível enviar LEMBRETE_EXAME para 2PHHl9t74ltZ8GvqaLKs
```

---

**Data de atualização:** 11/10/2025
**Versão do sistema:** 2.0 - Híbrido com Retry
