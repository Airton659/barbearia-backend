# routers/agendamentos.py
"""
Router para sistema de agendamentos
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
import schemas
import crud
from database import get_db
from auth import (
    get_current_user_firebase, get_current_profissional_user,
    validate_negocio_id
)
from firebase_admin import firestore

router = APIRouter(tags=["Agendamentos"])

@router.get("/profissionais/{profissional_id}/horarios-disponiveis")
def obter_horarios_disponiveis(
    profissional_id: str,
    data: str,  # formato YYYY-MM-DD
    negocio_id: str = Depends(validate_negocio_id),
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """Obtém os horários disponíveis de um profissional para uma data específica."""
    # Implementar lógica de horários disponíveis
    # Por enquanto, retornar uma lista mock
    return {
        "profissional_id": profissional_id,
        "data": data,
        "horarios_disponiveis": ["09:00", "10:00", "11:00", "14:00", "15:00", "16:00"]
    }

@router.post("/agendamentos", response_model=schemas.AgendamentoResponse)
def criar_agendamento(
    agendamento_data: schemas.AgendamentoCreate,
    negocio_id: str = Depends(validate_negocio_id),
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """Cria um novo agendamento para o cliente autenticado."""
    # Verificar se o usuário é cliente do negócio
    user_roles = current_user.roles or {}
    user_role = user_roles.get(negocio_id)
    
    if user_role not in ['cliente', 'admin']:
        raise HTTPException(
            status_code=403,
            detail="Apenas clientes podem criar agendamentos"
        )
    
    # Definir o negócio_id no agendamento
    agendamento_data.negocio_id = negocio_id
    
    return crud.criar_agendamento(db, agendamento_data, current_user)

@router.get("/agendamentos/me", response_model=List[schemas.AgendamentoResponse])
def listar_meus_agendamentos(
    negocio_id: str = Depends(validate_negocio_id),
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """Lista todos os agendamentos do cliente autenticado."""
    return crud.listar_agendamentos_por_cliente(db, negocio_id, current_user.id)

@router.delete("/agendamentos/{agendamento_id}", status_code=status.HTTP_200_OK)
def cancelar_agendamento_cliente(
    agendamento_id: str,
    negocio_id: str = Depends(validate_negocio_id),
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """Cancela um agendamento específico do cliente autenticado."""
    # Verificar se o agendamento pertence ao cliente
    agendamentos = crud.listar_agendamentos_por_cliente(db, negocio_id, current_user.id)
    agendamento_encontrado = None
    
    for agendamento in agendamentos:
        if agendamento['id'] == agendamento_id:
            agendamento_encontrado = agendamento
            break
    
    if not agendamento_encontrado:
        raise HTTPException(
            status_code=404,
            detail="Agendamento não encontrado ou não pertence a você"
        )
    
    # Verificar se pode ser cancelado (exemplo: só se for no futuro)
    if agendamento_encontrado['status'] == 'cancelado':
        raise HTTPException(
            status_code=400,
            detail="Agendamento já foi cancelado"
        )
    
    success = crud.cancelar_agendamento(db, agendamento_id, "Cancelado pelo cliente")
    if not success:
        raise HTTPException(
            status_code=500,
            detail="Não foi possível cancelar o agendamento"
        )
    
    return {"message": "Agendamento cancelado com sucesso"}


# Router para profissionais gerenciarem seus agendamentos
professional_router = APIRouter(prefix="/me", tags=["Profissional - Autogestão"])

@professional_router.get("/agendamentos", response_model=List[schemas.AgendamentoResponse])
def listar_agendamentos_profissional(
    negocio_id: str = Depends(validate_negocio_id),
    current_user: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """Lista todos os agendamentos do profissional autenticado."""
    # Buscar o profissional atual
    profissional = crud.buscar_profissional_por_uid(db, negocio_id, current_user.firebase_uid)
    if not profissional:
        raise HTTPException(status_code=404, detail="Perfil profissional não encontrado")
    
    return crud.listar_agendamentos_por_profissional(db, negocio_id, profissional['id'])

@professional_router.patch("/agendamentos/{agendamento_id}/cancelar", response_model=schemas.AgendamentoResponse)
def cancelar_agendamento_profissional(
    agendamento_id: str,
    dados_cancelamento: schemas.CancelamentoAgendamento,
    negocio_id: str = Depends(validate_negocio_id),
    current_user: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """Cancela um agendamento específico do profissional autenticado."""
    # Buscar o profissional atual
    profissional = crud.buscar_profissional_por_uid(db, negocio_id, current_user.firebase_uid)
    if not profissional:
        raise HTTPException(status_code=404, detail="Perfil profissional não encontrado")
    
    # Verificar se o agendamento pertence ao profissional
    agendamentos = crud.listar_agendamentos_por_profissional(db, negocio_id, profissional['id'])
    agendamento_encontrado = None
    
    for agendamento in agendamentos:
        if agendamento['id'] == agendamento_id:
            agendamento_encontrado = agendamento
            break
    
    if not agendamento_encontrado:
        raise HTTPException(
            status_code=404,
            detail="Agendamento não encontrado ou não pertence a você"
        )
    
    # Cancelar agendamento
    success = crud.cancelar_agendamento(db, agendamento_id, dados_cancelamento.motivo)
    if not success:
        raise HTTPException(
            status_code=500,
            detail="Não foi possível cancelar o agendamento"
        )
    
    # Retornar agendamento atualizado
    # Buscar novamente para retornar dados atualizados
    agendamentos_atualizados = crud.listar_agendamentos_por_profissional(db, negocio_id, profissional['id'])
    for agendamento in agendamentos_atualizados:
        if agendamento['id'] == agendamento_id:
            return agendamento
    
    raise HTTPException(status_code=500, detail="Erro ao recuperar agendamento atualizado")