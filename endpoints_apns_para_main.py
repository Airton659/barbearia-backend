"""
ENDPOINTS APNs PARA ADICIONAR NO main.py

Copie e cole estes endpoints no seu arquivo main.py para permitir
que o frontend registre e remova tokens APNs (Safari/iOS).

⚠️ ATENÇÃO: Verifique se você já tem as importações necessárias no topo do main.py:
    - from crud import adicionar_apns_token, remover_apns_token
    - import schemas
"""

# =============================================================================
# ENDPOINTS APNS - COPIE ESTES 2 ENDPOINTS PARA O main.py
# =============================================================================

@app.post("/api/usuarios/apns-token", tags=["Usuarios"])
async def registrar_token_apns(
    token_data: schemas.APNsTokenRequest,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db)
):
    """
    Registra um token APNs (Safari/iOS Web Push) para o usuário autenticado.

    Este endpoint é chamado pelo frontend quando um usuário Safari concede
    permissão para notificações e obtém um token APNs.

    Args:
        token_data: Objeto contendo o token APNs
        current_user: Usuário autenticado (injetado pelo Depends)
        db: Cliente Firestore (injetado pelo Depends)

    Returns:
        {"message": "Token APNs registrado com sucesso"}

    Exemplo de request:
        POST /api/usuarios/apns-token
        Headers: { "Authorization": "Bearer <token>" }
        Body: { "apns_token": "abc123..." }
    """
    adicionar_apns_token(db, current_user['firebase_uid'], token_data.apns_token)
    return {"message": "Token APNs registrado com sucesso"}


@app.delete("/api/usuarios/apns-token", tags=["Usuarios"])
async def remover_token_apns(
    token_data: schemas.APNsTokenRequest,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db)
):
    """
    Remove um token APNs do usuário autenticado.

    Este endpoint é chamado quando o usuário revoga permissão de notificações
    ou quando o token expira.

    Args:
        token_data: Objeto contendo o token APNs a ser removido
        current_user: Usuário autenticado (injetado pelo Depends)
        db: Cliente Firestore (injetado pelo Depends)

    Returns:
        {"message": "Token APNs removido com sucesso"}

    Exemplo de request:
        DELETE /api/usuarios/apns-token
        Headers: { "Authorization": "Bearer <token>" }
        Body: { "apns_token": "abc123..." }
    """
    remover_apns_token(db, current_user['firebase_uid'], token_data.apns_token)
    return {"message": "Token APNs removido com sucesso"}


# =============================================================================
# IMPORTAÇÕES NECESSÁRIAS (Adicione no topo do main.py se ainda não existir)
# =============================================================================

"""
Adicione estas linhas no topo do seu main.py (se ainda não existirem):

from crud import (
    # ... suas importações existentes ...
    adicionar_apns_token,
    remover_apns_token,
)
"""


# =============================================================================
# ENDPOINT OPCIONAL: Verificar configuração APNs (útil para debug)
# =============================================================================

@app.get("/api/apns/status", tags=["Debug"])
async def verificar_status_apns(
    current_user: dict = Depends(get_current_user)
):
    """
    Verifica se o serviço APNs está configurado e funcionando.

    Útil para debug e para verificar se tudo está OK antes de testar no Safari.

    Returns:
        {
            "apns_habilitado": bool,
            "topic": str,
            "sandbox": bool,
            "mensagem": str
        }
    """
    from apns_service import get_apns_service

    apns_service = get_apns_service()

    if apns_service.enabled:
        import os
        return {
            "apns_habilitado": True,
            "topic": apns_service.topic,
            "sandbox": os.getenv('APNS_USE_SANDBOX', 'False').lower() == 'true',
            "mensagem": "APNs está configurado e pronto para uso!"
        }
    else:
        return {
            "apns_habilitado": False,
            "topic": None,
            "sandbox": None,
            "mensagem": "APNs não está configurado. Verifique as variáveis de ambiente."
        }


# =============================================================================
# ENDPOINT OPCIONAL: Testar envio APNs (apenas para desenvolvimento)
# =============================================================================

@app.post("/api/apns/test", tags=["Debug"])
async def testar_envio_apns(
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db)
):
    """
    Envia uma notificação de teste para todos os tokens APNs do usuário atual.

    ⚠️ USE APENAS EM DESENVOLVIMENTO! Remova em produção.

    Returns:
        {
            "total_tokens": int,
            "sucessos": int,
            "falhas": int
        }
    """
    from notification_helper import enviar_notificacao_para_usuario

    # Busca o usuário atual
    usuario_doc = db.collection('usuarios').document(current_user['firebase_uid']).get()

    if not usuario_doc.exists:
        return {"error": "Usuário não encontrado"}

    usuario_data = usuario_doc.to_dict()
    apns_tokens = usuario_data.get('apns_tokens', [])

    if not apns_tokens:
        return {
            "total_tokens": 0,
            "sucessos": 0,
            "falhas": 0,
            "mensagem": "Você não tem tokens APNs registrados. Use Safari e permita notificações."
        }

    # Envia notificação de teste
    resultado = enviar_notificacao_para_usuario(
        usuario_data=usuario_data,
        titulo="Teste APNs",
        corpo="Esta é uma notificação de teste do sistema APNs! Se você está vendo isso, tudo está funcionando! 🎉",
        data_payload={
            "tipo": "TESTE_APNS",
            "timestamp": str(firestore.SERVER_TIMESTAMP)
        }
    )

    return {
        "total_tokens": len(apns_tokens),
        "sucessos": resultado['apns_sucessos'],
        "falhas": resultado['apns_falhas'],
        "mensagem": f"Teste concluído! {resultado['apns_sucessos']} de {len(apns_tokens)} notificações enviadas."
    }


# =============================================================================
# INSTRUÇÕES DE INSTALAÇÃO
# =============================================================================

"""
COMO ADICIONAR NO main.py:

1. Abra o arquivo main.py

2. Adicione as importações no topo (se ainda não existirem):

   from crud import (
       # ... suas importações existentes ...
       adicionar_apns_token,
       remover_apns_token,
   )

3. Copie e cole os 2 endpoints principais:
   - registrar_token_apns
   - remover_token_apns

4. (Opcional) Copie os endpoints de debug/teste:
   - verificar_status_apns
   - testar_envio_apns

5. Salve o arquivo

6. Reinicie o servidor:
   uvicorn main:app --reload

7. Teste no Swagger:
   http://localhost:8000/docs

8. Verifique se os novos endpoints aparecem na documentação:
   - POST /api/usuarios/apns-token
   - DELETE /api/usuarios/apns-token
   - GET /api/apns/status (se você adicionou)
   - POST /api/apns/test (se você adicionou)

PRONTO! Os endpoints estão funcionando.
"""
