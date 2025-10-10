# 🍎 Configuração do Apple Push Notifications (APNs) para Web Push

Guia completo para habilitar notificações push no Safari/iOS para o PWA.

---

## 📋 O QUE FOI IMPLEMENTADO

✅ **Backend Python** pronto para enviar notificações via APNs
✅ **Sistema Híbrido** que envia automaticamente para FCM (Android/Chrome) + APNs (Safari/iOS)
✅ **Sem quebrar nada** - O FCM continua funcionando exatamente como antes
✅ **Padrão de notificações** mantido - Mesmo formato de título/corpo/data

---

## 🔧 CONFIGURAÇÃO DO BACKEND

### Passo 1: Instalar a biblioteca APNs

```bash
pip install pyapns2==0.7.2
```

Ou simplesmente:

```bash
pip install -r requirements.txt
```

### Passo 2: Colocar o arquivo .p8 no servidor

Você tem o arquivo `AuthKey_UD85TPJ89Y.p8` que baixou do Apple Developer Console.

**Opção 1: Colocar na pasta do projeto**
```bash
# Copie o arquivo para a pasta do backend
cp ~/Downloads/AuthKey_UD85TPJ89Y.p8 /caminho/para/barbearia-backend/
```

**Opção 2: Colocar em pasta segura fora do projeto**
```bash
# Recomendado para produção
mkdir -p /etc/secrets/apns
cp ~/Downloads/AuthKey_UD85TPJ89Y.p8 /etc/secrets/apns/
chmod 600 /etc/secrets/apns/AuthKey_UD85TPJ89Y.p8
```

### Passo 3: Configurar variáveis de ambiente

Adicione estas variáveis ao seu arquivo `.env` ou ao sistema:

```bash
# APNs Configuration
APNS_KEY_PATH=/caminho/completo/para/AuthKey_UD85TPJ89Y.p8
APNS_KEY_ID=UD85TPJ89Y
APNS_TEAM_ID=M83XX73UUS
APNS_TOPIC=web.ygg.conciergeanalicegrubert
APNS_USE_SANDBOX=False
```

**Explicação:**
- `APNS_KEY_PATH`: Caminho absoluto para o arquivo .p8
- `APNS_KEY_ID`: ID da chave (está no nome do arquivo)
- `APNS_TEAM_ID`: ID do seu time na Apple
- `APNS_TOPIC`: Seu Web Push ID criado no portal Apple
- `APNS_USE_SANDBOX`: `False` para produção, `True` para desenvolvimento

### Passo 4: Testar a configuração

```bash
# Reinicie o servidor
uvicorn main:app --reload

# Você deve ver no log:
# ✅ APNs Service inicializado com sucesso (Topic: web.ygg.conciergeanalicegrubert, Sandbox: False)
```

Se você ver essa mensagem, tudo está funcionando! 🎉

---

## 🚀 COMO USAR NO CÓDIGO

### Opção 1: Usar o helper híbrido (RECOMENDADO)

Este é o jeito mais fácil. Ele envia automaticamente para FCM + APNs:

```python
from notification_helper import enviar_notificacao_para_usuario

# Busca o usuário
usuario_doc = db.collection('usuarios').document(usuario_id).get()
usuario_data = usuario_doc.to_dict()

# Envia notificação para TODOS os dispositivos do usuário (FCM + APNs)
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

print(f"FCM: {resultado['fcm_sucessos']} enviados")
print(f"APNs: {resultado['apns_sucessos']} enviados")
```

### Opção 2: Controle manual (quando você já tem as listas de tokens)

```python
from notification_helper import enviar_notificacao_hibrida

# Você já tem as listas separadas
fcm_tokens = usuario_data.get('fcm_tokens', [])
apns_tokens = usuario_data.get('apns_tokens', [])

# Envia para ambos
resultado = enviar_notificacao_hibrida(
    fcm_tokens=fcm_tokens,
    apns_tokens=apns_tokens,
    titulo="Tarefa Atrasada",
    corpo="A tarefa do paciente Rocky está atrasada.",
    data_payload={"tipo": "TAREFA_ATRASADA", "tarefa_id": "789"}
)
```

### Opção 3: Apenas APNs (quando você só quer Safari)

```python
from apns_service import get_apns_service

apns_service = get_apns_service()

for token in apns_tokens:
    apns_service.send_notification(
        token=token,
        titulo="Novo Relatório",
        corpo="Um novo relatório foi criado.",
        data_payload={"tipo": "NOVO_RELATORIO", "id": "999"}
    )
```

---

## 🔌 ENDPOINTS DA API (PARA O FRONTEND)

### Registrar token APNs (Safari)

```python
# Adicione este endpoint no main.py:

from crud import adicionar_apns_token, remover_apns_token

@app.post("/api/usuarios/apns-token")
async def registrar_token_apns(
    token_data: schemas.APNsTokenRequest,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db)
):
    """Registra um token APNs (Safari/iOS) para o usuário"""
    adicionar_apns_token(db, current_user['firebase_uid'], token_data.apns_token)
    return {"message": "Token APNs registrado com sucesso"}

@app.delete("/api/usuarios/apns-token")
async def remover_token_apns(
    token_data: schemas.APNsTokenRequest,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db)
):
    """Remove um token APNs do usuário"""
    remover_apns_token(db, current_user['firebase_uid'], token_data.apns_token)
    return {"message": "Token APNs removido com sucesso"}
```

---

## 🔄 MIGRAR CÓDIGO EXISTENTE (OPCIONAL)

Se você quiser migrar suas funções de notificação existentes para usar o sistema híbrido:

### ANTES (apenas FCM):

```python
# Código antigo
tokens_fcm = criador_data.get('fcm_tokens', [])

if tokens_fcm:
    for token in tokens_fcm:
        try:
            message = messaging.Message(
                notification=messaging.Notification(title=titulo, body=corpo),
                data=data_payload,
                token=token
            )
            messaging.send(message)
        except Exception as e:
            logger.error(f"Erro: {e}")
```

### DEPOIS (FCM + APNs):

```python
# Código novo
from notification_helper import enviar_notificacao_para_usuario

resultado = enviar_notificacao_para_usuario(
    usuario_data=criador_data,
    titulo=titulo,
    corpo=corpo,
    data_payload=data_payload
)
```

**IMPORTANTE:** Você NÃO precisa migrar tudo de uma vez. O FCM continua funcionando!
Só migre quando for conveniente.

---

## 🧪 COMO TESTAR

### 1. Testar se o APNs está funcionando

```bash
# Rode o servidor
uvicorn main:app --reload

# Se você ver este log, está OK:
# ✅ APNs Service inicializado com sucesso
```

### 2. Testar envio de notificação

Crie um script de teste:

```python
# test_apns.py
from apns_service import get_apns_service

apns = get_apns_service()

if apns.enabled:
    print("✅ APNs está habilitado!")

    # Teste com um token real do Safari (você vai pegar do frontend)
    token = "COLE_UM_TOKEN_AQUI"

    sucesso = apns.send_notification(
        token=token,
        titulo="Teste",
        corpo="Esta é uma notificação de teste!",
        data_payload={"tipo": "TESTE"}
    )

    if sucesso:
        print("✅ Notificação enviada!")
    else:
        print("❌ Erro ao enviar")
else:
    print("❌ APNs não está habilitado. Verifique as variáveis de ambiente.")
```

---

## 🆘 TROUBLESHOOTING

### Problema: "APNs desabilitado"

**Causa:** Variável `APNS_KEY_PATH` não configurada ou arquivo não encontrado.

**Solução:**
```bash
# Verifique se o arquivo existe
ls -la /caminho/para/AuthKey_UD85TPJ89Y.p8

# Verifique se a variável está setada
echo $APNS_KEY_PATH

# Configure a variável
export APNS_KEY_PATH=/caminho/completo/para/AuthKey_UD85TPJ89Y.p8
```

### Problema: "Erro ao enviar notificação APNs"

**Possíveis causas:**
1. Token inválido (gerado incorretamente no Safari)
2. Topic errado (verifique se é `web.ygg.conciergeanalicegrubert`)
3. Certificado expirado (verifique no Apple Developer Console)
4. Sandbox vs Produção (troque `APNS_USE_SANDBOX`)

### Problema: "Notificação não aparece no Safari"

**Checklist:**
- [ ] Safari versão 16.4+ (Web Push só funciona a partir dessa versão)
- [ ] HTTPS habilitado (obrigatório)
- [ ] Permissão concedida pelo usuário
- [ ] Service Worker registrado corretamente
- [ ] Token enviado para o backend

---

## 📊 ESTRUTURA DE DADOS NO FIRESTORE

Após a implementação, os documentos de usuários terão:

```javascript
{
  "id": "user123",
  "nome": "João Silva",
  "email": "joao@example.com",
  "fcm_tokens": [
    "token_android_1",
    "token_chrome_1"
  ],
  "apns_tokens": [  // ← NOVO CAMPO
    "token_safari_1",
    "token_ios_web_1"
  ]
}
```

---

## 🔒 SEGURANÇA

### Protegendo o arquivo .p8

```bash
# Em produção, use permissões restritas
chmod 600 /caminho/para/AuthKey_UD85TPJ89Y.p8
chown seu_usuario:seu_grupo /caminho/para/AuthKey_UD85TPJ89Y.p8
```

### Não commitar o arquivo

Adicione ao `.gitignore`:

```
# .gitignore
*.p8
AuthKey_*.p8
```

### Usar variáveis de ambiente

Nunca coloque credenciais no código. Sempre use `.env`:

```bash
# .env (NÃO COMMITAR!)
APNS_KEY_PATH=/etc/secrets/apns/AuthKey_UD85TPJ89Y.p8
APNS_KEY_ID=UD85TPJ89Y
APNS_TEAM_ID=M83XX73UUS
APNS_TOPIC=web.ygg.conciergeanalicegrubert
```

---

## ✅ CHECKLIST DE IMPLEMENTAÇÃO

### Backend:
- [x] Instalado `pyapns2`
- [x] Criado `apns_service.py`
- [x] Criado `notification_helper.py`
- [x] Adicionado campo `apns_tokens` nos schemas
- [x] Criado funções `adicionar_apns_token` e `remover_apns_token`
- [ ] Colocado arquivo `.p8` no servidor
- [ ] Configurado variáveis de ambiente
- [ ] Criado endpoints `/api/usuarios/apns-token`
- [ ] Testado envio de notificação

### Frontend (próximo passo):
- [ ] Detectar Safari/iOS
- [ ] Pedir permissão de notificação
- [ ] Obter token APNs
- [ ] Enviar token para o backend via API
- [ ] Configurar Service Worker
- [ ] Testar recebimento de notificações

---

## 🎯 PRÓXIMOS PASSOS

1. **Configure as variáveis de ambiente** no servidor
2. **Reinicie o servidor** e verifique os logs
3. **Implemente o frontend** (vou te ajudar com isso depois)
4. **Teste no Safari** (macOS 13+ ou iOS 16.4+)

---

## 📞 DÚVIDAS?

- **Web Push ID está correto?** Sim: `web.ygg.conciergeanalicegrubert`
- **Precisa de app nativo?** Não! É só Web Push
- **Funciona em todos os Safaris?** Não, apenas Safari 16.4+ (abril 2023+)
- **Precisa de certificado separado para dev/prod?** Não, o mesmo .p8 serve para ambos
- **Como testar localmente?** Configure `APNS_USE_SANDBOX=True` e use um domínio de teste com HTTPS

---

**🎉 Tudo pronto no backend! Agora você só precisa:**
1. Colocar o arquivo `.p8` no servidor
2. Configurar as variáveis de ambiente
3. Reiniciar o servidor
4. Implementar o frontend (próximo passo)
