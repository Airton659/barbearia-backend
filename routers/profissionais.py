# routers/profissionais.py
"""
Router para gestão de profissionais e serviços
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List
import schemas
import crud
from database import get_db
from auth import (
    get_current_user_firebase, get_current_profissional_user,
    validate_negocio_id
)
from firebase_admin import firestore

# Router para endpoints públicos de profissionais
public_router = APIRouter(tags=["Profissionais"])

@public_router.get("/profissionais", response_model=List[schemas.ProfissionalResponse])
def listar_profissionais(
    negocio_id: str = Depends(validate_negocio_id),
    db: firestore.client = Depends(get_db)
):
    """Lista todos os profissionais de um negócio."""
    return crud.listar_profissionais_por_negocio(db, negocio_id)

@public_router.get("/profissionais/{profissional_id}", response_model=schemas.ProfissionalResponse)
def obter_profissional(
    profissional_id: str,
    negocio_id: str = Depends(validate_negocio_id),
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """Obtém detalhes de um profissional específico."""
    profissional = crud.buscar_profissional_por_id(db, profissional_id)
    if not profissional:
        raise HTTPException(status_code=404, detail="Profissional não encontrado")
    
    # Verificar se pertence ao mesmo negócio
    if profissional.get('negocio_id') != negocio_id:
        raise HTTPException(status_code=403, detail="Profissional não pertence a este negócio")
    
    return profissional


# Router para autogestão do profissional
self_management_router = APIRouter(prefix="/me", tags=["Profissional - Autogestão"])

@self_management_router.get("/profissional", response_model=schemas.ProfissionalResponse)
def obter_meu_perfil_profissional(
    negocio_id: str = Depends(validate_negocio_id),
    current_user: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """Obtém o perfil profissional do usuário autenticado."""
    profissional = crud.buscar_profissional_por_uid(db, negocio_id, current_user.firebase_uid)
    if not profissional:
        raise HTTPException(status_code=404, detail="Perfil profissional não encontrado")
    return profissional

@self_management_router.put("/profissional", response_model=schemas.ProfissionalResponse)
def atualizar_meu_perfil_profissional(
    update_data: schemas.ProfissionalUpdate,
    negocio_id: str = Depends(validate_negocio_id),
    current_user: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """Atualiza o perfil profissional do usuário autenticado."""
    # Buscar o profissional atual
    profissional = crud.buscar_profissional_por_uid(db, negocio_id, current_user.firebase_uid)
    if not profissional:
        raise HTTPException(status_code=404, detail="Perfil profissional não encontrado")
    
    # Atualizar
    updated_profissional = crud.atualizar_perfil_profissional(db, profissional['id'], update_data)
    if not updated_profissional:
        raise HTTPException(status_code=500, detail="Não foi possível atualizar o perfil")
    
    return updated_profissional

@self_management_router.post("/servicos", response_model=schemas.ServicoResponse, status_code=status.HTTP_201_CREATED)
def criar_meu_servico(
    servico_data: schemas.ServicoCreate,
    negocio_id: str = Depends(validate_negocio_id),
    current_user: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """Cria um novo serviço para o profissional autenticado."""
    # Buscar o profissional atual
    profissional = crud.buscar_profissional_por_uid(db, negocio_id, current_user.firebase_uid)
    if not profissional:
        raise HTTPException(status_code=404, detail="Perfil profissional não encontrado")
    
    # Definir o profissional_id no serviço
    servico_data.profissional_id = profissional['id']
    
    return crud.criar_servico(db, servico_data)

@self_management_router.get("/servicos", response_model=List[schemas.ServicoResponse])
def listar_meus_servicos(
    negocio_id: str = Depends(validate_negocio_id),
    current_user: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """Lista todos os serviços do profissional autenticado."""
    # Buscar o profissional atual
    profissional = crud.buscar_profissional_por_uid(db, negocio_id, current_user.firebase_uid)
    if not profissional:
        raise HTTPException(status_code=404, detail="Perfil profissional não encontrado")
    
    return crud.listar_servicos_por_profissional(db, profissional['id'])

@self_management_router.put("/servicos/{servico_id}", response_model=schemas.ServicoResponse)
def atualizar_meu_servico(
    servico_id: str,
    update_data: schemas.ServicoUpdate,
    negocio_id: str = Depends(validate_negocio_id),
    current_user: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """Atualiza um serviço específico do profissional autenticado."""
    # Buscar o profissional atual
    profissional = crud.buscar_profissional_por_uid(db, negocio_id, current_user.firebase_uid)
    if not profissional:
        raise HTTPException(status_code=404, detail="Perfil profissional não encontrado")
    
    # Atualizar serviço
    updated_servico = crud.atualizar_servico(db, servico_id, profissional['id'], update_data)
    if not updated_servico:
        raise HTTPException(status_code=404, detail="Serviço não encontrado ou não pertence a você")
    
    return updated_servico

@self_management_router.delete("/servicos/{servico_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_meu_servico(
    servico_id: str,
    negocio_id: str = Depends(validate_negocio_id),
    current_user: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """Remove um serviço específico do profissional autenticado."""
    # Buscar o profissional atual
    profissional = crud.buscar_profissional_por_uid(db, negocio_id, current_user.firebase_uid)
    if not profissional:
        raise HTTPException(status_code=404, detail="Perfil profissional não encontrado")
    
    # Deletar serviço
    success = crud.deletar_servico(db, servico_id, profissional['id'])
    if not success:
        raise HTTPException(status_code=404, detail="Serviço não encontrado ou não pertence a você")

@self_management_router.post("/horarios-trabalho", response_model=List[schemas.HorarioTrabalho])
def definir_horarios_trabalho(
    horarios: List[schemas.HorarioTrabalho],
    negocio_id: str = Depends(validate_negocio_id),
    current_user: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """Define os horários de trabalho do profissional autenticado."""
    # Buscar o profissional atual
    profissional = crud.buscar_profissional_por_uid(db, negocio_id, current_user.firebase_uid)
    if not profissional:
        raise HTTPException(status_code=404, detail="Perfil profissional não encontrado")
    
    # Implementar lógica de definir horários (não implementada no CRUD ainda)
    # Por enquanto, retornar os horários recebidos
    return horarios

@self_management_router.get("/horarios-trabalho", response_model=List[schemas.HorarioTrabalho])
def obter_meus_horarios_trabalho(
    negocio_id: str = Depends(validate_negocio_id),
    current_user: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """Obtém os horários de trabalho do profissional autenticado."""
    # Buscar o profissional atual
    profissional = crud.buscar_profissional_por_uid(db, negocio_id, current_user.firebase_uid)
    if not profissional:
        raise HTTPException(status_code=404, detail="Perfil profissional não encontrado")
    
    return crud.listar_horarios_trabalho(db, profissional['id'])

@self_management_router.post("/bloqueios", response_model=schemas.Bloqueio)
def criar_bloqueio_horario(
    bloqueio_data: schemas.Bloqueio,
    negocio_id: str = Depends(validate_negocio_id),
    current_user: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """Cria um bloqueio de horário para o profissional autenticado."""
    # Buscar o profissional atual
    profissional = crud.buscar_profissional_por_uid(db, negocio_id, current_user.firebase_uid)
    if not profissional:
        raise HTTPException(status_code=404, detail="Perfil profissional não encontrado")
    
    return crud.criar_bloqueio(db, profissional['id'], bloqueio_data)

@self_management_router.delete("/bloqueios/{bloqueio_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover_bloqueio_horario(
    bloqueio_id: str,
    negocio_id: str = Depends(validate_negocio_id),
    current_user: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """Remove um bloqueio de horário do profissional autenticado."""
    # Buscar o profissional atual
    profissional = crud.buscar_profissional_por_uid(db, negocio_id, current_user.firebase_uid)
    if not profissional:
        raise HTTPException(status_code=404, detail="Perfil profissional não encontrado")
    
    success = crud.deletar_bloqueio(db, profissional['id'], bloqueio_id)
    if not success:
        raise HTTPException(status_code=404, detail="Bloqueio não encontrado ou não pertence a você")

@self_management_router.get("/pacientes", response_model=List[schemas.PacienteProfile])
def listar_meus_pacientes(
    negocio_id: str = Depends(validate_negocio_id),
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """
    (Gestor, Enfermeiro ou Técnico)
    Lista os pacientes. Para Gestores, retorna TODOS os pacientes do negócio.
    Para Enfermeiros/Técnicos, retorna apenas os pacientes vinculados.
    """
    user_role = current_user.roles.get(negocio_id)
    
    if user_role not in ["profissional", "tecnico", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado: seu perfil não tem permissão para visualizar pacientes."
        )

    pacientes = crud.listar_pacientes_por_profissional_ou_tecnico(db, negocio_id, current_user.id, user_role)
    return pacientes