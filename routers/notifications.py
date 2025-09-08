# routers/notifications.py
"""
Router para sistema de notificações
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
import schemas
import crud
from database import get_db
from auth import get_current_user_firebase, validate_negocio_id
from firebase_admin import firestore

router = APIRouter(tags=["Notificações"])

@router.get("/notificacoes", response_model=List[schemas.NotificacaoResponse])
def listar_notificacoes(
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """Lista todas as notificações do usuário autenticado."""
    return crud.listar_notificacoes(db, current_user.id)

@router.get("/notificacoes/nao-lidas/contagem", response_model=schemas.NotificacaoContagemResponse)
def contar_notificacoes_nao_lidas(
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """Retorna a contagem de notificações não lidas."""
    notificacoes = crud.listar_notificacoes(db, current_user.id)
    nao_lidas = sum(1 for notif in notificacoes if not notif.get('lida', False))
    
    return {
        "total_nao_lidas": nao_lidas,
        "usuario_id": current_user.id
    }

@router.post("/notificacoes/ler-todas", status_code=status.HTTP_204_NO_CONTENT)
def marcar_todas_como_lidas(
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """Marca todas as notificações do usuário como lidas."""
    # Buscar todas as notificações não lidas do usuário
    query = db.collection('notificacoes') \
             .where('usuario_id', '==', current_user.id) \
             .where('lida', '==', False)
    
    # Marcar todas como lidas
    batch = db.batch()
    for doc in query.stream():
        batch.update(doc.reference, {'lida': True, 'data_leitura': firestore.SERVER_TIMESTAMP})
    
    batch.commit()

@router.post("/notificacoes/agendar", response_model=schemas.NotificacaoAgendadaResponse)
def agendar_notificacao(
    notificacao_data: schemas.NotificacaoAgendadaCreate,
    negocio_id: str = Depends(validate_negocio_id),
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """Agenda uma notificação para ser enviada em um horário específico."""
    # Verificar se o usuário tem permissão para agendar notificações
    user_roles = current_user.roles or {}
    user_role = user_roles.get(negocio_id)
    
    if user_role not in ['admin', 'profissional']:
        raise HTTPException(
            status_code=403,
            detail="Apenas administradores e profissionais podem agendar notificações"
        )
    
    # Criar notificação agendada
    notif_dict = {
        'titulo': notificacao_data.titulo,
        'mensagem': notificacao_data.mensagem,
        'tipo': notificacao_data.tipo,
        'data_agendada': notificacao_data.data_agendada,
        'negocio_id': negocio_id,
        'criado_por': current_user.id,
        'status': 'agendada',
        'created_at': firestore.SERVER_TIMESTAMP
    }
    
    # Adicionar destinatários se especificados
    if notificacao_data.usuario_ids:
        notif_dict['usuario_ids'] = notificacao_data.usuario_ids
    
    doc_ref = db.collection('notificacoes_agendadas').document()
    doc_ref.set(notif_dict)
    notif_dict['id'] = doc_ref.id
    
    return notif_dict

@router.post("/notificacoes/marcar-como-lida", status_code=status.HTTP_204_NO_CONTENT)
def marcar_notificacao_como_lida(
    request: schemas.NotificacaoLidaRequest,
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """Marca uma notificação específica como lida."""
    # Buscar a notificação
    notif_ref = db.collection('notificacoes').document(request.notificacao_id)
    notif_doc = notif_ref.get()
    
    if not notif_doc.exists:
        raise HTTPException(status_code=404, detail="Notificação não encontrada")
    
    notif_data = notif_doc.to_dict()
    
    # Verificar se a notificação pertence ao usuário
    if notif_data.get('usuario_id') != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Você não tem permissão para marcar esta notificação como lida"
        )
    
    # Marcar como lida
    notif_ref.update({
        'lida': True,
        'data_leitura': firestore.SERVER_TIMESTAMP
    })