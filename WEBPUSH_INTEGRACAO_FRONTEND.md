# 🔔 Integração Web Push VAPID - Notificações Agendadas

## ⚠️ IMPORTANTE
Esta implementação usa **sistema híbrido VAPID + FCM** para notificações agendadas:

### Notificações com Web Push VAPID + FCM (híbrido):
- ✅ **LEMBRETE_EXAME** - Lembrete 1h antes do exame (ou 09:00 se sem horário)
- ✅ **TAREFA_ATRASADA** - Quando tarefa não é concluída no prazo
- ✅ **LEMBRETE_AGENDADO** - Notificações manuais agendadas para data/hora específica

### Notificações que continuam apenas FCM + APNs:
- TAREFA_CONCLUIDA (instantânea)
- EXAME_CRIADO (instantânea)
- SUPORTE_ADICIONADO (instantânea)
- Todas as outras notificações instantâneas

---

## 📋 O que é Web Push VAPID?

- **Mais confiável** que FCM para notificações agendadas
- **Token mais estável** (não expira facilmente como FCM)
- **Funciona offline** (navegador recebe mesmo com aba fechada)
- **Padrão Web** (Chrome, Firefox, Safari iOS 16.4+, Edge)

## 🔄 Como funciona o sistema híbrido?

```
Notificação Agendada (ex: LEMBRETE_EXAME)
    ↓
1. Backend tenta enviar via Web Push VAPID
    ├─ Sucesso → ✅ Usuário recebe (token estável)
    └─ Falha (sem subscription VAPID)
        ↓
2. Fallback: Envia via FCM
    └─ ✅ Usuário recebe (compatibilidade com quem não configurou VAPID)
```

**Vantagens:**
- ✅ **Usuários novos** com VAPID configurado: Token estável, funciona após 15 dias
- ✅ **Usuários antigos** sem VAPID: Continuam recebendo via FCM
- ✅ **Transição suave**: Sem quebrar nada, migração gradual

---

## 🚀 Implementação Frontend

### 1. Buscar chave pública VAPID

```javascript
async function getVapidPublicKey() {
  const response = await fetch('https://SEU-BACKEND.com/vapid-public-key');
  const data = await response.json();
  return data.publicKey;
}
```

### 2. Registrar Service Worker

Crie o arquivo `public/sw.js`:

```javascript
// public/sw.js
self.addEventListener('push', event => {
  if (!event.data) return;

  const payload = event.data.json();
  const { title, body, data, tag } = payload;

  const options = {
    body: body,
    icon: '/icon-192x192.png',
    badge: '/badge-72x72.png',
    tag: tag,
    data: data,
    requireInteraction: true // Notificação fica até usuário interagir
  };

  event.waitUntil(
    self.registration.showNotification(title, options)
  );
});

self.addEventListener('notificationclick', event => {
  event.notification.close();

  const data = event.notification.data;

  // Redirecionar conforme tipo de notificação
  if (data.tipo === 'LEMBRETE_EXAME') {
    event.waitUntil(
      clients.openWindow(`/exames/${data.exame_id}`)
    );
  } else if (data.tipo === 'TAREFA_ATRASADA') {
    event.waitUntil(
      clients.openWindow(`/tarefas/${data.tarefa_id}`)
    );
  } else if (data.tipo === 'LEMBRETE_AGENDADO') {
    event.waitUntil(
      clients.openWindow('/notificacoes')
    );
  }
});
```

### 3. Pedir permissão e fazer subscription

```javascript
// No componente/página principal do app
async function setupWebPushForExames(userId) {
  try {
    // 1. Verificar se navegador suporta
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
      console.warn('Web Push não suportado neste navegador');
      return;
    }

    // 2. Registrar service worker
    const registration = await navigator.serviceWorker.register('/sw.js');
    await navigator.serviceWorker.ready;

    // 3. Pedir permissão
    const permission = await Notification.requestPermission();
    if (permission !== 'granted') {
      console.log('Permissão de notificação negada');
      return;
    }

    // 4. Buscar chave VAPID
    const vapidPublicKey = await getVapidPublicKey();

    // 5. Fazer subscription
    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(vapidPublicKey)
    });

    // 6. Enviar subscription para o backend
    await fetch(`https://SEU-BACKEND.com/usuarios/${userId}/webpush-subscription`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        endpoint: subscription.endpoint,
        keys: {
          p256dh: arrayBufferToBase64(subscription.getKey('p256dh')),
          auth: arrayBufferToBase64(subscription.getKey('auth'))
        }
      })
    });

    console.log('✅ Web Push configurado para notificações agendadas');

  } catch (error) {
    console.error('Erro ao configurar Web Push:', error);
  }
}

// Funções auxiliares
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

### 4. Chamar no login/inicialização do app

```javascript
// Quando usuário faz login ou app inicializa
useEffect(() => {
  if (user && user.id) {
    setupWebPushForExames(user.id);
  }
}, [user]);
```

### 5. Remover subscription (opcional)

```javascript
async function removeWebPushSubscription(userId) {
  const registration = await navigator.serviceWorker.getRegistration();
  const subscription = await registration.pushManager.getSubscription();

  if (subscription) {
    await subscription.unsubscribe();
  }

  await fetch(`https://SEU-BACKEND.com/usuarios/${userId}/webpush-subscription`, {
    method: 'DELETE'
  });
}
```

---

## 🧪 Como Testar

### Teste LEMBRETE_EXAME:
1. **No navegador:** Abra DevTools → Application → Service Workers
2. **Verifique se** o SW está registrado
3. **Crie um exame** para daqui a 1h05min (ex: se agora são 14:00, crie para 15:10)
4. **Aguarde** o scheduler rodar (a cada 15 minutos)
5. **Notificação deve chegar** mesmo com aba fechada!

### Teste TAREFA_ATRASADA:
1. Crie uma tarefa com prazo passado (ou aguarde uma tarefa atrasar)
2. O scheduler roda a cada 15 minutos
3. Notificação de tarefa atrasada deve chegar

### Teste LEMBRETE_AGENDADO:
1. Use o endpoint de criar notificação agendada
2. Configure para data/hora futura
3. Aguarde o horário agendado
4. Notificação deve chegar

---

## 📊 Endpoints Backend

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/vapid-public-key` | Retorna chave pública VAPID |
| POST | `/usuarios/{id}/webpush-subscription` | Salva subscription do usuário |
| DELETE | `/usuarios/{id}/webpush-subscription` | Remove subscription |

---

## 🔒 Segurança

- ✅ Chaves VAPID armazenadas no backend (nunca expor private key)
- ✅ Subscription específica por usuário
- ✅ Validação de origem via VAPID
- ✅ Remoção automática de subscriptions expiradas (HTTP 410)

---

## 📱 Compatibilidade

| Plataforma | Web Push VAPID | FCM Fallback |
|------------|----------------|--------------|
| **Android Chrome** | ✅ Funciona | ✅ Fallback |
| **Android Firefox** | ✅ Funciona | ✅ Fallback |
| **iOS Safari 16.4+** | ✅ Funciona | ✅ Fallback |
| **Desktop Chrome** | ✅ Funciona | ✅ Fallback |
| **Desktop Firefox** | ✅ Funciona | ✅ Fallback |
| **Desktop Edge** | ✅ Funciona | ✅ Fallback |

---

## ❓ FAQ

**P: Funciona em modo incógnito?**
R: Sim, mas subscription se perde ao fechar navegador.

**P: Funciona no iOS?**
R: Sim, a partir do iOS 16.4 (Safari). Se falhar, usa FCM como fallback.

**P: E se o usuário negar permissão?**
R: Notificação fica salva no Firestore + tenta enviar via FCM. Usuário vê quando abrir o app.

**P: Token Web Push expira?**
R: Muito raramente. Se expirar, backend remove automaticamente e usa FCM como fallback.

**P: Preciso migrar todas as notificações?**
R: Não! Apenas notificações agendadas usam VAPID. Notificações instantâneas continuam com FCM/APNs.

**P: O que acontece se o usuário não configurar VAPID?**
R: Sistema continua funcionando normalmente via FCM (modo compatibilidade).

---

## 🎉 Pronto!

Agora as notificações agendadas usam sistema híbrido Web Push VAPID + FCM:
- **VAPID primeiro** (token estável, resolve problema dos 15 dias)
- **FCM como fallback** (compatibilidade com quem não configurou)
- **Notificações instantâneas** continuam usando FCM + APNs normalmente
