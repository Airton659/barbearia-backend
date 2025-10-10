# 📝 Exemplo de Migração de Código FCM para FCM + APNs

Este documento mostra **como migrar** uma função existente de notificação para usar o sistema híbrido.

⚠️ **IMPORTANTE:** Isso é **OPCIONAL**. O FCM continua funcionando normalmente!

---

## 🔍 Cenário: Função `aprovar_relatorio`

Vamos pegar a função de exemplo do seu guia de notificações.

### ❌ ANTES (Apenas FCM)

```python
def aprovar_relatorio(db: firestore.client, relatorio_id: str, medico_id: str) -> Optional[Dict]:
    """
    Muda o status de um relatório para 'aprovado' e notifica o criador.
    """
    print(f"--- INICIANDO APROVAÇÃO DO RELATÓRIO {relatorio_id} ---")

    # ... (código de validação) ...

    # PASSO 1: Coletar IDs
    criado_por_id = relatorio.get('criado_por_id')
    paciente_id = relatorio.get('paciente_id')

    # PASSO 2: Buscar Dados Completos
    medico_doc = db.collection('usuarios').document(medico_id).get()
    nome_medico = decrypt_data(medico_doc.to_dict().get('nome', ''))

    paciente_doc = db.collection('usuarios').document(paciente_id).get()
    nome_paciente = decrypt_data(paciente_doc.to_dict().get('nome', ''))

    criador_doc = db.collection('usuarios').document(criado_por_id).get()
    criador_data = criador_doc.to_dict()
    tokens_fcm = criador_data.get('fcm_tokens', [])

    # PASSO 3: Construir a Mensagem
    titulo = "Relatório Avaliado"
    corpo = f"O Dr(a). {nome_medico} aprovou o relatório do paciente {nome_paciente}."

    # PASSO 4: Construir os Dados
    data_payload = {
        "tipo": "RELATORIO_AVALIADO",
        "relatorio_id": relatorio.get('id', ''),
        "paciente_id": str(paciente_id),
        "status": "aprovado",
    }

    # PASSO 5: Persistir no Histórico
    db.collection('usuarios').document(criado_por_id).collection('notificacoes').add({
        "title": titulo,
        "body": corpo,
        "tipo": "RELATORIO_AVALIADO",
        "relacionado": {
            "relatorio_id": relatorio.get('id'),
            "paciente_id": paciente_id
        },
        "lida": False,
        "data_criacao": firestore.SERVER_TIMESTAMP
    })

    # PASSO 6: Enviar o Push (APENAS FCM)
    if tokens_fcm:
        sucessos = 0
        for token in tokens_fcm:
            try:
                message = messaging.Message(
                    notification=messaging.Notification(title=titulo, body=corpo),
                    data=data_payload,
                    token=token
                )
                messaging.send(message)
                sucessos += 1
            except Exception as e:
                logger.error(f"Erro ao enviar para o token {token[:10]}...: {e}")
        print(f"Envio concluído. Sucessos: {sucessos}")

    return relatorio
```

---

### ✅ DEPOIS (FCM + APNs Híbrido)

Só mude o **PASSO 6**:

```python
from notification_helper import enviar_notificacao_para_usuario

def aprovar_relatorio(db: firestore.client, relatorio_id: str, medico_id: str) -> Optional[Dict]:
    """
    Muda o status de um relatório para 'aprovado' e notifica o criador.
    """
    print(f"--- INICIANDO APROVAÇÃO DO RELATÓRIO {relatorio_id} ---")

    # ... (código de validação) ...

    # PASSO 1: Coletar IDs
    criado_por_id = relatorio.get('criado_por_id')
    paciente_id = relatorio.get('paciente_id')

    # PASSO 2: Buscar Dados Completos
    medico_doc = db.collection('usuarios').document(medico_id).get()
    nome_medico = decrypt_data(medico_doc.to_dict().get('nome', ''))

    paciente_doc = db.collection('usuarios').document(paciente_id).get()
    nome_paciente = decrypt_data(paciente_doc.to_dict().get('nome', ''))

    criador_doc = db.collection('usuarios').document(criado_por_id).get()
    criador_data = criador_doc.to_dict()

    # PASSO 3: Construir a Mensagem
    titulo = "Relatório Avaliado"
    corpo = f"O Dr(a). {nome_medico} aprovou o relatório do paciente {nome_paciente}."

    # PASSO 4: Construir os Dados
    data_payload = {
        "tipo": "RELATORIO_AVALIADO",
        "relatorio_id": relatorio.get('id', ''),
        "paciente_id": str(paciente_id),
        "status": "aprovado",
    }

    # PASSO 5: Persistir no Histórico
    db.collection('usuarios').document(criado_por_id).collection('notificacoes').add({
        "title": titulo,
        "body": corpo,
        "tipo": "RELATORIO_AVALIADO",
        "relacionado": {
            "relatorio_id": relatorio.get('id'),
            "paciente_id": paciente_id
        },
        "lida": False,
        "data_criacao": firestore.SERVER_TIMESTAMP
    })

    # PASSO 6: Enviar o Push (FCM + APNs) ← ÚNICA MUDANÇA!
    resultado = enviar_notificacao_para_usuario(
        usuario_data=criador_data,
        titulo=titulo,
        corpo=corpo,
        data_payload=data_payload
    )

    print(
        f"Envio concluído. "
        f"FCM: {resultado['fcm_sucessos']}/{resultado['fcm_sucessos'] + resultado['fcm_falhas']}, "
        f"APNs: {resultado['apns_sucessos']}/{resultado['apns_sucessos'] + resultado['apns_falhas']}"
    )

    return relatorio
```

---

## 📊 Comparação

| Aspecto | ANTES (FCM) | DEPOIS (Híbrido) | Mudanças |
|---------|-------------|------------------|----------|
| **Passos 1-5** | Iguais | Iguais | ✅ Zero |
| **Passo 6** | Loop manual FCM | Função helper | ✨ 1 linha |
| **Tokens FCM** | `tokens_fcm = ...` | Não precisa | ✅ Simplificou |
| **Tokens APNs** | Não existia | Automático | ✨ Novo |
| **Código** | ~15 linhas | ~3 linhas | ✅ -80% |
| **Funcionalidade** | Apenas Android/Chrome | Todos os browsers | ✨ +Safari/iOS |

---

## 🎯 O Que Mudou?

### 1. Importação
```python
from notification_helper import enviar_notificacao_para_usuario
```

### 2. Passo 6 simplificado
**Antes:** Loop manual de 15 linhas
**Depois:** 1 chamada de função

### 3. Resultado detalhado
Agora você sabe exatamente quantas notificações foram enviadas para cada plataforma.

---

## 🔄 Outras Funções para Migrar

Procure no seu código por este padrão:

```python
tokens_fcm = usuario_data.get('fcm_tokens', [])

if tokens_fcm:
    for token in tokens_fcm:
        try:
            message = messaging.Message(...)
            messaging.send(message)
```

Troque por:

```python
from notification_helper import enviar_notificacao_para_usuario

resultado = enviar_notificacao_para_usuario(
    usuario_data=usuario_data,
    titulo=titulo,
    corpo=corpo,
    data_payload=data_payload
)
```

---

## ⚙️ Funções que podem ser migradas

Baseado no seu `crud.py`, estas funções podem usar o helper:

1. ✅ `_notificar_cliente_cancelamento`
2. ✅ `_notificar_cliente_confirmacao`
3. ✅ `_notificar_criador_relatorio_avaliado`
4. ✅ `_notificar_tecnicos_plano_atualizado`
5. ✅ `_notificar_profissional_associacao`
6. ✅ `_notificar_checklist_concluido`
7. ✅ `_notificar_medico_novo_relatorio`
8. ✅ `_notificar_enfermeiro_novo_registro_diario`
9. ✅ `_notificar_tarefa_concluida`
10. ✅ `_notificar_tarefa_atrasada`
11. ✅ `_notificar_paciente_exame_criado`
12. ✅ `_notificar_paciente_suporte_adicionado`
13. ✅ `processar_notificacoes_agendadas`

**Total:** 13 funções que podem se beneficiar do helper.

---

## 🚀 Vantagens da Migração

### Antes (FCM Manual)
```python
# 15 linhas de código
tokens_fcm = criador_data.get('fcm_tokens', [])
if tokens_fcm:
    sucessos = 0
    for token in tokens_fcm:
        try:
            message = messaging.Message(
                notification=messaging.Notification(title=titulo, body=corpo),
                data=data_payload,
                token=token
            )
            messaging.send(message)
            sucessos += 1
        except Exception as e:
            logger.error(f"Erro: {e}")
    print(f"Sucessos: {sucessos}")
```

### Depois (Helper Híbrido)
```python
# 3 linhas de código
resultado = enviar_notificacao_para_usuario(
    usuario_data=criador_data, titulo=titulo, corpo=corpo, data_payload=data_payload
)
```

✅ **Menos código**
✅ **Mais funcionalidades** (Safari/iOS)
✅ **Mais fácil de manter**
✅ **Logs automáticos**
✅ **Tratamento de erros incluído**

---

## ⚠️ IMPORTANTE: Não Precisa Migrar Tudo de Uma Vez

O sistema é **100% retrocompatível**:

- ✅ Código antigo (FCM manual) continua funcionando
- ✅ Código novo (helper híbrido) também funciona
- ✅ Você pode migrar função por função
- ✅ Você pode não migrar nada se não quiser

**O APNs só será usado se:**
1. O usuário tiver `apns_tokens` cadastrados
2. Você usar o helper híbrido OU chamar o `apns_service` diretamente

Se você não fizer nada, **tudo continua funcionando como antes**.

---

## 🧪 Como Testar Após Migrar

1. **Teste com usuário Chrome (FCM):**
   - Deve continuar recebendo notificações normalmente
   - Nada muda para eles

2. **Teste com usuário Safari (APNs):**
   - Depois que o frontend registrar o token APNs
   - Deve receber notificação no Safari
   - Dados devem estar corretos

3. **Teste com usuário multi-dispositivo:**
   - Usuário com Chrome + Safari
   - Ambos devem receber a mesma notificação
   - Verifique os contadores no log

---

## 📝 Checklist de Migração por Função

Para cada função que você decidir migrar:

- [ ] Identificar onde está o loop de FCM
- [ ] Importar `enviar_notificacao_para_usuario`
- [ ] Substituir o loop pela chamada da função
- [ ] Ajustar o log de sucesso (opcional)
- [ ] Testar com usuário FCM (Chrome/Android)
- [ ] Testar com usuário APNs (Safari/iOS)
- [ ] Commitar as mudanças

---

## 🎯 Recomendação

**Não migre agora.** Primeiro:

1. Configure o APNs no servidor
2. Implemente o frontend
3. Teste com alguns usuários Safari
4. Depois, migre gradualmente (ou não migre)

O sistema foi feito para **coexistir** com o código antigo. 🎉

---

## 💡 Dica: Quando NÃO Usar o Helper

Se você já tem lógicas complexas de notificação (como envio em lote para múltiplos usuários), pode ser melhor usar o `enviar_notificacao_hibrida` diretamente:

```python
from notification_helper import enviar_notificacao_hibrida

# Coleta tokens de múltiplos usuários
all_fcm_tokens = []
all_apns_tokens = []

for usuario in usuarios:
    all_fcm_tokens.extend(usuario.get('fcm_tokens', []))
    all_apns_tokens.extend(usuario.get('apns_tokens', []))

# Envia para todos de uma vez
resultado = enviar_notificacao_hibrida(
    fcm_tokens=all_fcm_tokens,
    apns_tokens=all_apns_tokens,
    titulo=titulo,
    corpo=corpo,
    data_payload=data_payload
)
```

---

**🎉 Agora você sabe como migrar! Mas lembre-se: é opcional.**
