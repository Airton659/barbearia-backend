# routers/servicos.py
"""
Router para serviços e horários disponíveis
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List
from datetime import date
import schemas
import crud
from database import get_db
from auth import get_current_user_firebase, validate_negocio_id
from firebase_admin import firestore

router = APIRouter(tags=["Serviços", "Horários"])

@router.get("/servicos", response_model=List[schemas.ServicoResponse])
def listar_servicos_publicos(
    negocio_id: str = Depends(validate_negocio_id),
    db: firestore.client = Depends(get_db)
):
    """Lista todos os serviços disponíveis de um negócio."""
    return crud.listar_servicos_por_negocio(db, negocio_id)

@router.get("/servicos/{servico_id}", response_model=schemas.ServicoResponse)
def obter_servico(
    servico_id: str,
    negocio_id: str = Depends(validate_negocio_id),
    db: firestore.client = Depends(get_db)
):
    """Obtém detalhes de um serviço específico."""
    servico = crud.buscar_servico_por_id(db, servico_id)
    if not servico:
        raise HTTPException(status_code=404, detail="Serviço não encontrado")
    
    # Verificar se pertence ao mesmo negócio
    if servico.get('negocio_id') != negocio_id:
        raise HTTPException(status_code=403, detail="Serviço não pertence a este negócio")
    
    return servico

@router.get("/profissionais/{profissional_id}/horarios-disponiveis")
def calcular_horarios_disponiveis(
    profissional_id: str,
    dia: date = Query(..., description="Data para consultar horários (YYYY-MM-DD)"),
    duracao_servico: int = Query(30, description="Duração do serviço em minutos"),
    negocio_id: str = Depends(validate_negocio_id),
    db: firestore.client = Depends(get_db)
):
    """Calcula e retorna os horários livres de um profissional em um dia específico."""
    return crud.calcular_horarios_disponiveis(db, profissional_id, dia, duracao_servico)

@router.get("/servicos/{servico_id}/profissionais", response_model=List[schemas.ProfissionalResponse])
def listar_profissionais_por_servico(
    servico_id: str,
    negocio_id: str = Depends(validate_negocio_id),
    db: firestore.client = Depends(get_db)
):
    """Lista todos os profissionais que oferecem um serviço específico."""
    return crud.listar_profissionais_por_servico(db, servico_id, negocio_id)