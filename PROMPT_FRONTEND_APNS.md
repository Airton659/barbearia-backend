# 🍎 Implementar Apple Push Notifications no Frontend Flutter Web

---

## 📋 CONTEXTO

Tenho um **PWA (Progressive Web App)** desenvolvido em Flutter Web que já usa **Firebase Cloud Messaging (FCM)** para notificações push. Funciona perfeitamente em Android e Chrome, mas **não funciona no Safari/iOS** porque o Safari não suporta FCM.

O **BACKEND JÁ ESTÁ 100% PRONTO** com suporte a APNs. Agora preciso implementar o **frontend** para:
1. Detectar quando o usuário está no Safari/iOS
2. Pedir permissão de notificação usando a API nativa do Safari
3. Obter o token APNs (Web Push)
4. Enviar o token para o backend
5. Receber notificações no Safari

---

## ✅ O QUE JÁ ESTÁ FUNCIONANDO (BACKEND)

### Endpoints disponíveis:

**Base URL:** `https://barbearia-backend-service-862082955632.southamerica-east1.run.app`

1. **POST /me/register-apns-token** (autenticado)
   - Registra token APNs do Safari
   - Body: `{ "apns_token": "string" }`
   - Headers: `Authorization: Bearer {firebase_token}`
   - Response: `{ "message": "APNs token registrado com sucesso." }`

2. **DELETE /me/remove-apns-token** (autenticado)
   - Remove token APNs
   - Body: `{ "apns_token": "string" }`
   - Headers: `Authorization: Bearer {firebase_token}`
   - Response: `{ "message": "APNs token removido com sucesso." }`

3. **GET /apns/status** (público)
   - Verifica se APNs está funcionando
   - Response:
   ```json
   {
     "apns_habilitado": true,
     "topic": "web.ygg.conciergeanalicegrubert",
     "sandbox": false,
     "mensagem": "✅ APNs está configurado e pronto para uso!"
   }
   ```

### Backend envia notificações para:
- ✅ FCM (Android/Chrome/Edge) - continua funcionando
- ✅ APNs (Safari/iOS) - agora também funciona!

---

## 🎯 O QUE PRECISO IMPLEMENTAR NO FRONTEND

### 1️⃣ DETECÇÃO DE BROWSER

Preciso de código Dart/JavaScript para:

1. **Detectar se o usuário está no Safari (macOS ou iOS)**
   ```dart
   // Função que retorna true se for Safari
   bool isSafari() {
     // Como detectar Safari vs Chrome/Edge?
     // Safari no macOS
     // Safari no iOS
     // Safari Mobile
   }
   ```

2. **Detectar a versão do Safari**
   ```dart
   // Web Push só funciona no Safari 16.4+
   bool isSafariCompatibleWithWebPush() {
     // Como verificar a versão?
   }
   ```

---

### 2️⃣ PERMISSÃO DE NOTIFICAÇÃO (SAFARI)

No Safari, a API de notificação é **diferente** do FCM. Preciso:

1. **Pedir permissão usando a API nativa do Safari**
   ```javascript
   // Service Worker ou código JavaScript
   // Como pedir permissão corretamente no Safari?
   // Como saber se o usuário já concedeu/negou permissão?
   ```

2. **Obter o token APNs (Web Push)**
   ```javascript
   // Depois que o usuário aceitar, como obter o token?
   // Exemplo:
   navigator.serviceWorker.ready.then(registration => {
     registration.pushManager.subscribe({
       userVisibleOnly: true,
       applicationServerKey: '???' // Qual chave usar aqui?
     }).then(subscription => {
       // Como extrair o token daqui?
       const token = ???;
     });
   });
   ```

---

### 3️⃣ REGISTRO DO TOKEN NO BACKEND

Preciso de código Dart para:

1. **Enviar o token APNs para o backend**
   ```dart
   // Função para registrar token Safari
   Future<void> registerApnsToken(String apnsToken) async {
     // Como fazer a requisição POST?
     // Endpoint: /me/register-apns-token
     // Headers: Authorization com Firebase Auth token
     // Body: { "apns_token": apnsToken }
   }
   ```

2. **Integrar com o código atual de notificações**
   ```dart
   // Atualmente tenho:
   class NotificationService {
     final FirebaseMessaging _firebaseMessaging = FirebaseMessaging.instance;

     Future<void> initialize() async {
       // Pede permissão FCM
       // Obtém token FCM
       // Envia para backend
     }
   }

   // Como adaptar para:
   // - Detectar Safari
   // - Se Safari: usar APNs
   // - Se não: continuar usando FCM
   ```

---

### 4️⃣ SERVICE WORKER

Estrutura atual do frontend:
```
frontend/web/
  ├── index.html
  ├── manifest.json
  └── firebase-messaging-sw.js (Service Worker atual do FCM)
```

**Service Worker atual (firebase-messaging-sw.js):**
```javascript
importScripts('https://www.gstatic.com/firebasejs/9.0.0/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/9.0.0/firebase-messaging-compat.js');

firebase.initializeApp({
  apiKey: "...",
  projectId: "...",
  messagingSenderId: "...",
  appId: "..."
});

const messaging = firebase.messaging();

messaging.onBackgroundMessage((payload) => {
  console.log('Received background message ', payload);
  const notificationTitle = payload.notification.title;
  const notificationOptions = {
    body: payload.notification.body,
    icon: '/icons/icon-192.png'
  };
  self.registration.showNotification(notificationTitle, notificationOptions);
});
```

**Preciso:**

1. **Adaptar o Service Worker para suportar Safari**
   ```javascript
   // Como detectar se a notificação veio do FCM ou APNs?
   // Como processar notificações APNs?
   // Preciso de Service Worker separado para Safari?
   ```

2. **Processar notificações APNs**
   ```javascript
   // Quando uma notificação APNs chegar, como processar?
   self.addEventListener('push', event => {
     // Como saber se é FCM ou APNs?
     // Como extrair título e corpo da notificação?
     // Como mostrar a notificação?
   });
   ```

---

### 5️⃣ MANIFEST.JSON E INDEX.HTML

**manifest.json atual:**
```json
{
  "name": "Meu PWA",
  "short_name": "PWA",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#ffffff",
  "theme_color": "#000000",
  "icons": [
    {
      "src": "/icons/icon-192.png",
      "sizes": "192x192",
      "type": "image/png"
    }
  ]
}
```

**Preciso:**

1. **O que adicionar/modificar no manifest.json para Safari?**
   ```json
   // Precisa de configurações específicas para APNs?
   // Algum campo especial para Safari/iOS?
   ```

2. **Meta tags necessárias no index.html?**
   ```html
   <!-- Tem alguma meta tag específica para Safari Web Push? -->
   <!-- Precisa declarar o Service Worker de forma diferente? -->
   ```

---

## 📝 INFORMAÇÕES ADICIONAIS DO BACKEND

### Credenciais APNs configuradas:
- **Web Push ID (Topic):** `web.ygg.conciergeanalicegrubert`
- **Team ID:** `M83XX73UUS`
- **Key ID:** `UD85TPJ89Y`
- **Arquivo .p8:** Já configurado no backend (Secret Manager GCP)
- **Ambiente:** Produção (não sandbox)

### Como o backend envia notificações:

O backend usa um **helper híbrido** que envia automaticamente para FCM + APNs:

```python
from notification_helper import enviar_notificacao_para_usuario

# Busca o usuário (que tem fcm_tokens e apns_tokens)
usuario_data = {
  "fcm_tokens": ["token_chrome_1", "token_android_1"],
  "apns_tokens": ["token_safari_1", "token_ios_1"]
}

# Envia para TODOS os dispositivos
resultado = enviar_notificacao_para_usuario(
    usuario_data=usuario_data,
    titulo="Relatório Avaliado",
    corpo="O Dr(a). House aprovou o relatório do paciente Rocky.",
    data_payload={
        "tipo": "RELATORIO_AVALIADO",
        "relatorio_id": "123",
        "paciente_id": "456"
    }
)

# Resultado:
# {"fcm_sucessos": 2, "fcm_falhas": 0, "apns_sucessos": 2, "apns_falhas": 0}
```

**Formato da notificação APNs que o Safari receberá:**

```json
{
  "aps": {
    "alert": {
      "title": "Relatório Avaliado",
      "body": "O Dr(a). House aprovou o relatório do paciente Rocky."
    },
    "sound": "default"
  },
  "tipo": "RELATORIO_AVALIADO",
  "relatorio_id": "123",
  "paciente_id": "456"
}
```

---

## 🎯 OBJETIVO FINAL

Após a implementação, o sistema deve funcionar assim:

### **Cenário 1: Usuário abre o PWA no Chrome/Android**
1. ✅ Detecta que é Chrome
2. ✅ Usa Firebase Messaging (FCM)
3. ✅ Obtém token FCM
4. ✅ Envia para `/me/register-fcm-token`
5. ✅ Recebe notificações via FCM (já funciona)

### **Cenário 2: Usuário abre o PWA no Safari/iOS**
1. ⏳ Detecta que é Safari
2. ⏳ Verifica se Safari 16.4+
3. ⏳ Pede permissão usando API nativa Safari
4. ⏳ Obtém token APNs (Web Push)
5. ⏳ Envia para `/me/register-apns-token`
6. ⏳ Recebe notificações via APNs

### **Cenário 3: Usuário tem múltiplos dispositivos**
1. Chrome Desktop → token FCM 1
2. Android App → token FCM 2
3. Safari macOS → token APNs 1
4. Safari iOS → token APNs 2
5. Backend armazena todos e envia para todos simultaneamente

---

## 📊 FORMATO DE RESPOSTA ESPERADO

### PARTE 1: Detecção de Safari
```dart
// Código Dart completo e comentado
// Função isSafari()
// Função isSafariCompatibleWithWebPush()
```

### PARTE 2: Service Worker
```javascript
// Código JavaScript completo do Service Worker
// Adaptado para suportar FCM + APNs
// Com comentários explicando cada parte
```

### PARTE 3: Registro de Token APNs
```dart
// Código Dart completo
// Função para obter token APNs
// Função para enviar para backend
// Integração com NotificationService existente
```

### PARTE 4: Manifest e Index.html
```json
// manifest.json completo
```
```html
<!-- index.html com meta tags necessárias -->
```

### PARTE 5: Checklist de Teste
```
[ ] Testar detecção de Safari no macOS
[ ] Testar detecção de Safari no iOS
[ ] Testar permissão de notificação no Safari Desktop
[ ] Testar permissão de notificação no Safari Mobile
[ ] Verificar se token APNs é obtido corretamente
[ ] Verificar se token é enviado para backend
[ ] Testar recebimento de notificação no Safari Desktop
[ ] Testar recebimento de notificação no Safari Mobile (iOS 16.4+)
[ ] Testar notificação com app instalado na Home Screen
[ ] Verificar se FCM continua funcionando no Chrome/Android
```

---

## ⚠️ RESTRIÇÕES TÉCNICAS

- **Frontend:** Flutter Web 3.x
- **Safari mínimo:** 16.4+ (abril 2023) - Web Push só funciona a partir dessa versão
- **HTTPS obrigatório:** Já tenho (domínio em produção)
- **Service Worker:** Precisa estar registrado corretamente
- **Compatibilidade:** Deve funcionar em Safari macOS e Safari iOS

---

## 🚫 O QUE NÃO PRECISO

- ❌ App nativo iOS
- ❌ Xcode
- ❌ Swift/Objective-C
- ❌ Publicar na App Store
- ❌ Modificar o backend (já está pronto)

---

## ❓ DÚVIDAS ESPECÍFICAS

1. **applicationServerKey**: Qual chave usar no `pushManager.subscribe()`? É o Web Push ID? Team ID?
2. **Token format**: O token APNs que o Safari gera é uma string simples? Precisa processar/converter?
3. **Service Worker**: Posso usar o mesmo `firebase-messaging-sw.js` ou preciso criar outro arquivo?
4. **Push event**: Como saber se a notificação que chegou é FCM ou APNs no Service Worker?
5. **Teste local**: Como testar localmente? Safari permite localhost?
6. **Permissions API**: Safari suporta `Notification.requestPermission()` ou precisa de API diferente?

---

## 📞 INFORMAÇÕES DISPONÍVEIS

- ✅ Backend 100% pronto e testado
- ✅ Endpoints documentados e funcionando
- ✅ APNs configurado no GCP
- ✅ Web Push ID criado no Apple Developer Console
- ✅ Chave .p8 configurada
- ✅ Domínio com HTTPS em produção

**URL de teste do backend:** https://barbearia-backend-service-862082955632.southamerica-east1.run.app/apns/status

---

## 🎯 RESUMO DO QUE PRECISO

**EM RESUMO, PRECISO DE:**

1. 📱 Código para **detectar Safari/iOS**
2. 🔔 Código para **pedir permissão de notificação no Safari**
3. 🎫 Código para **obter token APNs (Web Push)**
4. 📤 Código para **enviar token para o backend**
5. 🔧 **Service Worker adaptado** para processar notificações APNs
6. 📄 **Manifest.json e index.html** com configurações necessárias
7. ✅ **Checklist de testes** para validar tudo

**IMPORTANTE:** O código deve ser **completo, comentado e pronto para copiar/colar**. Preciso de um tutorial passo a passo, como se eu nunca tivesse mexido com Web Push no Safari antes.

---

**Por favor, seja o mais detalhado possível. Sou desenvolvedor Flutter, mas nunca implementei Web Push nativo do Safari. Preciso de um guia completo do zero até funcionar.**

🙏 Obrigado!
