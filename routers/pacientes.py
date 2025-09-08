# routers/pacientes.py
"""
Router para gestão de pacientes, fichas médicas e anamneses
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List
import schemas
import crud
from database import get_db
from auth import (
    get_current_user_firebase, get_current_admin_or_profissional_user,
    get_current_tecnico_user, get_paciente_autorizado,
    get_paciente_autorizado_anamnese, validate_negocio_id
)
from firebase_admin import firestore
from datetime import date

router = APIRouter(tags=["Ficha do Paciente", "Pacientes", "Anamnese", "Fluxo do Técnico"])

# =================================================================================
# ENDPOINTS DE FICHA DO PACIENTE
# =================================================================================

@router.get("/pacientes/{paciente_id}/ficha-completa", response_model=schemas.FichaCompletaResponse)
def obter_ficha_completa(
    paciente_id: str,
    consulta_id: str = Query(None, description="Opcional: força o retorno da consulta informada"),
    current_user: schemas.UsuarioProfile = Depends(get_paciente_autorizado),
    db: firestore.client = Depends(get_db)
):
    """Retorna a ficha clínica completa do paciente (sem os exames)."""
    if consulta_id:
        return {
            "consultas": crud.listar_consultas(db, paciente_id),
            "medicacoes": crud.listar_medicacoes(db, paciente_id, consulta_id),
            "checklist": crud.listar_checklist(db, paciente_id, consulta_id),
            "orientacoes": crud.listar_orientacoes(db, paciente_id, consulta_id),
        }
    return crud.get_ficha_completa_paciente(db, paciente_id)

@router.post("/pacientes/{paciente_id}/exames", response_model=schemas.ExameResponse, status_code=status.HTTP_201_CREATED)
def criar_exame_paciente(
    paciente_id: str,
    exame_data: schemas.ExameCreate,
    current_user: schemas.UsuarioProfile = Depends(get_current_admin_or_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """Cria um novo exame para um paciente."""
    exame_data.paciente_id = paciente_id
    return crud.criar_exame(db, exame_data)

@router.put("/pacientes/{paciente_id}/exames/{exame_id}", response_model=schemas.ExameResponse)
def atualizar_exame_paciente(
    paciente_id: str,
    exame_id: str,
    update_data: schemas.ExameUpdate,
    negocio_id: str = Depends(validate_negocio_id),
    current_user: schemas.UsuarioProfile = Depends(get_current_admin_or_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """Atualiza um exame, com verificação de permissão."""
    try:
        exame_atualizado = crud.update_exame(db, paciente_id, exame_id, update_data, current_user, negocio_id)
        if not exame_atualizado:
            raise HTTPException(status_code=404, detail="Exame não encontrado")
        return exame_atualizado
    except HTTPException:
        raise

@router.delete("/pacientes/{paciente_id}/exames/{exame_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_exame_paciente(
    paciente_id: str,
    exame_id: str,
    current_user: schemas.UsuarioProfile = Depends(get_current_admin_or_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """Remove um exame da ficha do paciente."""
    success = crud.delete_exame(db, paciente_id, exame_id)
    if not success:
        raise HTTPException(status_code=404, detail="Exame não encontrado")

@router.post("/pacientes/{paciente_id}/medicacoes", response_model=schemas.MedicacaoResponse, status_code=status.HTTP_201_CREATED)
def criar_medicacao_paciente(
    paciente_id: str,
    medicacao_data: schemas.MedicacaoCreate,
    consulta_id: str = Query(..., description="ID da consulta"),
    current_user: schemas.UsuarioProfile = Depends(get_current_admin_or_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """Cria uma nova medicação para um paciente."""
    return crud.criar_medicacao(db, medicacao_data, consulta_id)

@router.patch("/pacientes/{paciente_id}/medicacoes/{medicacao_id}", response_model=schemas.MedicacaoResponse)
def atualizar_medicacao_paciente(
    paciente_id: str,
    medicacao_id: str,
    update_data: schemas.MedicacaoUpdate,
    current_user: schemas.UsuarioProfile = Depends(get_current_admin_or_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """Atualiza uma medicação na ficha do paciente."""
    medicacao_atualizada = crud.update_medicacao(db, paciente_id, medicacao_id, update_data)
    if not medicacao_atualizada:
        raise HTTPException(status_code=404, detail="Medicação não encontrada")
    return medicacao_atualizada

@router.delete("/pacientes/{paciente_id}/medicacoes/{medicacao_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_medicacao_paciente(
    paciente_id: str,
    medicacao_id: str,
    current_user: schemas.UsuarioProfile = Depends(get_current_admin_or_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """Remove uma medicação da ficha do paciente."""
    success = crud.delete_medicacao(db, paciente_id, medicacao_id)
    if not success:
        raise HTTPException(status_code=404, detail="Medicação não encontrada")

@router.post("/pacientes/{paciente_id}/checklist-itens", response_model=schemas.ChecklistItemResponse, status_code=status.HTTP_201_CREATED)
def criar_item_checklist_paciente(
    paciente_id: str,
    item_data: schemas.ChecklistItemCreate,
    consulta_id: str = Query(..., description="ID da consulta"),
    current_user: schemas.UsuarioProfile = Depends(get_current_admin_or_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """Cria um novo item do checklist para um paciente."""
    return crud.criar_checklist_item(db, item_data, consulta_id)

@router.patch("/pacientes/{paciente_id}/checklist-itens/{item_id}", response_model=schemas.ChecklistItemResponse)
def atualizar_item_checklist_paciente(
    paciente_id: str,
    item_id: str,
    update_data: schemas.ChecklistItemUpdate,
    current_user: schemas.UsuarioProfile = Depends(get_current_admin_or_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """Atualiza um item do checklist na ficha do paciente."""
    item_atualizado = crud.update_checklist_item(db, paciente_id, item_id, update_data)
    if not item_atualizado:
        raise HTTPException(status_code=404, detail="Item do checklist não encontrado")
    return item_atualizado

@router.delete("/pacientes/{paciente_id}/checklist-itens/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_item_checklist_paciente(
    paciente_id: str,
    item_id: str,
    current_user: schemas.UsuarioProfile = Depends(get_current_admin_or_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """Remove um item do checklist da ficha do paciente."""
    success = crud.delete_checklist_item(db, paciente_id, item_id)
    if not success:
        raise HTTPException(status_code=404, detail="Item do checklist não encontrado")

@router.patch("/pacientes/{paciente_id}/consultas/{consulta_id}", response_model=schemas.ConsultaResponse)
def atualizar_consulta_paciente(
    paciente_id: str,
    consulta_id: str,
    update_data: schemas.ConsultaUpdate,
    current_user: schemas.UsuarioProfile = Depends(get_paciente_autorizado),
    db: firestore.client = Depends(get_db)
):
    """Atualiza uma consulta na ficha do paciente."""
    consulta_atualizada = crud.update_consulta(db, paciente_id, consulta_id, update_data)
    if not consulta_atualizada:
        raise HTTPException(status_code=404, detail="Consulta não encontrada")
    return consulta_atualizada

@router.delete("/pacientes/{paciente_id}/consultas/{consulta_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_consulta_paciente(
    paciente_id: str,
    consulta_id: str,
    current_user: schemas.UsuarioProfile = Depends(get_current_admin_or_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """Remove uma consulta da ficha do paciente."""
    success = crud.delete_consulta(db, paciente_id, consulta_id)
    if not success:
        raise HTTPException(status_code=404, detail="Consulta não encontrada")

@router.patch("/pacientes/{paciente_id}/orientacoes/{orientacao_id}", response_model=schemas.OrientacaoResponse)
def atualizar_orientacao_paciente(
    paciente_id: str,
    orientacao_id: str,
    update_data: schemas.OrientacaoUpdate,
    current_user: schemas.UsuarioProfile = Depends(get_current_admin_or_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """Atualiza uma orientação na ficha do paciente."""
    orientacao_atualizada = crud.update_orientacao(db, paciente_id, orientacao_id, update_data)
    if not orientacao_atualizada:
        raise HTTPException(status_code=404, detail="Orientação não encontrada")
    return orientacao_atualizada

@router.delete("/pacientes/{paciente_id}/orientacoes/{orientacao_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_orientacao_paciente(
    paciente_id: str,
    orientacao_id: str,
    current_user: schemas.UsuarioProfile = Depends(get_current_admin_or_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """Remove uma orientação da ficha do paciente."""
    success = crud.delete_orientacao(db, paciente_id, orientacao_id)
    if not success:
        raise HTTPException(status_code=404, detail="Orientação não encontrada")

@router.post("/pacientes/{paciente_id}/consultas", response_model=schemas.ConsultaResponse, status_code=status.HTTP_201_CREATED)
def criar_consulta_paciente(
    paciente_id: str,
    consulta_data: schemas.ConsultaCreate,
    current_user: schemas.UsuarioProfile = Depends(get_current_admin_or_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """Cria uma nova consulta para um paciente."""
    consulta_data.paciente_id = paciente_id
    return crud.criar_consulta(db, consulta_data)

@router.get("/pacientes/{paciente_id}/consultas", response_model=List[schemas.ConsultaResponse])
def listar_consultas_paciente(
    paciente_id: str,
    current_user: schemas.UsuarioProfile = Depends(get_paciente_autorizado),
    db: firestore.client = Depends(get_db)
):
    """Lista todas as consultas de um paciente."""
    return crud.listar_consultas(db, paciente_id)

@router.get("/pacientes/{paciente_id}/orientacoes", response_model=List[schemas.OrientacaoResponse])
def listar_orientacoes_paciente(
    paciente_id: str,
    consulta_id: str = Query(..., description="ID da consulta"),
    current_user: schemas.UsuarioProfile = Depends(get_paciente_autorizado),
    db: firestore.client = Depends(get_db)
):
    """Lista todas as orientações de uma consulta específica."""
    return crud.listar_orientacoes(db, paciente_id, consulta_id)

@router.post("/pacientes/{paciente_id}/orientacoes", response_model=schemas.OrientacaoResponse, status_code=status.HTTP_201_CREATED)
def criar_orientacao_paciente(
    paciente_id: str,
    orientacao_data: schemas.OrientacaoCreate,
    consulta_id: str = Query(..., description="ID da consulta"),
    current_user: schemas.UsuarioProfile = Depends(get_current_admin_or_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """Cria uma nova orientação para um paciente."""
    return crud.criar_orientacao(db, orientacao_data, consulta_id)

@router.get("/pacientes/{paciente_id}/exames", response_model=List[schemas.ExameResponse])
def listar_exames_paciente(
    paciente_id: str,
    current_user: schemas.UsuarioProfile = Depends(get_paciente_autorizado),
    db: firestore.client = Depends(get_db)
):
    """Lista todos os exames de um paciente."""
    return crud.listar_exames(db, paciente_id)

@router.get("/pacientes/{paciente_id}/medicacoes", response_model=List[schemas.MedicacaoResponse])
def listar_medicacoes_paciente(
    paciente_id: str,
    consulta_id: str = Query(..., description="ID da consulta"),
    current_user: schemas.UsuarioProfile = Depends(get_paciente_autorizado),
    db: firestore.client = Depends(get_db)
):
    """Lista todas as medicações de uma consulta específica."""
    return crud.listar_medicacoes(db, paciente_id, consulta_id)

@router.get("/pacientes/{paciente_id}/checklist-itens", response_model=List[schemas.ChecklistItemResponse])
def listar_checklist_paciente(
    paciente_id: str,
    consulta_id: str = Query(..., description="ID da consulta"),
    current_user: schemas.UsuarioProfile = Depends(get_paciente_autorizado),
    db: firestore.client = Depends(get_db)
):
    """Lista todos os itens do checklist de uma consulta específica."""
    return crud.listar_checklist(db, paciente_id, consulta_id)

# =================================================================================
# ENDPOINTS DE ANAMNESE
# =================================================================================

@router.post("/pacientes/{paciente_id}/anamnese", response_model=schemas.AnamneseResponse, status_code=status.HTTP_201_CREATED)
def criar_anamnese_paciente(
    paciente_id: str,
    anamnese_data: schemas.AnamneseCreate,
    current_user: schemas.UsuarioProfile = Depends(get_paciente_autorizado_anamnese),
    db: firestore.client = Depends(get_db)
):
    """Cria uma nova anamnese para um paciente."""
    return crud.criar_anamnese(db, paciente_id, anamnese_data)

@router.get("/pacientes/{paciente_id}/anamnese", response_model=List[schemas.AnamneseResponse])
def listar_anamneses_paciente(
    paciente_id: str,
    current_user: schemas.UsuarioProfile = Depends(get_paciente_autorizado_anamnese),
    db: firestore.client = Depends(get_db)
):
    """Lista todas as anamneses de um paciente."""
    return crud.listar_anamneses_por_paciente(db, paciente_id)

@router.put("/anamnese/{anamnese_id}", response_model=schemas.AnamneseResponse)
def atualizar_anamnese(
    anamnese_id: str,
    update_data: schemas.AnamneseUpdate,
    paciente_id: str = Query(..., description="ID do paciente"),
    current_user: schemas.UsuarioProfile = Depends(get_paciente_autorizado_anamnese),
    db: firestore.client = Depends(get_db)
):
    """Atualiza uma anamnese específica."""
    result = crud.atualizar_anamnese(db, anamnese_id, paciente_id, update_data)
    if not result:
        raise HTTPException(status_code=404, detail="Anamnese não encontrada")
    return result

# =================================================================================
# ENDPOINTS DE DADOS PESSOAIS DO PACIENTE
# =================================================================================

@router.put("/pacientes/{paciente_id}/dados-pessoais", response_model=schemas.PacienteProfile)
def atualizar_dados_pessoais_paciente(
    paciente_id: str,
    dados_pessoais: schemas.PacienteUpdateDadosPessoais,
    current_user: schemas.UsuarioProfile = Depends(get_paciente_autorizado),
    db: firestore.client = Depends(get_db)
):
    """Atualiza os dados pessoais de um paciente."""
    result = crud.atualizar_dados_pessoais_paciente(db, paciente_id, dados_pessoais)
    if not result:
        raise HTTPException(status_code=404, detail="Paciente não encontrado")
    return result

@router.put("/pacientes/{paciente_id}/endereco", response_model=schemas.UsuarioProfile)
def atualizar_endereco_paciente(
    paciente_id: str,
    endereco_data: schemas.EnderecoUpdate,
    current_user: schemas.UsuarioProfile = Depends(get_paciente_autorizado),
    db: firestore.client = Depends(get_db)
):
    """Atualiza o endereço de um paciente."""
    result = crud.atualizar_endereco_paciente(db, paciente_id, endereco_data)
    if not result:
        raise HTTPException(status_code=404, detail="Paciente não encontrado")
    return result

# =================================================================================
# ENDPOINTS DO FLUXO DO TÉCNICO
# =================================================================================

@router.get("/pacientes/{paciente_id}/checklist-diario", response_model=List[schemas.ChecklistItemDiarioResponse])
def listar_checklist_diario_paciente(
    paciente_id: str,
    dia: date = Query(..., description="Data do checklist (YYYY-MM-DD)"),
    negocio_id: str = Depends(validate_negocio_id),
    current_user: schemas.UsuarioProfile = Depends(get_current_tecnico_user),
    db: firestore.client = Depends(get_db)
):
    """Lista o checklist diário de um paciente para uma data específica."""
    try:
        # Usar função do CRUD que já implementa a replicação de itens
        checklist = crud.listar_checklist_diario_com_replicacao(db, paciente_id, dia, negocio_id)
        return checklist
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao carregar checklist diário: {str(e)}")

@router.patch("/pacientes/{paciente_id}/checklist-diario/{item_id}", response_model=schemas.ChecklistItemDiarioResponse)
def atualizar_item_checklist_diario(
    paciente_id: str,
    item_id: str,
    update_data: schemas.ChecklistItemDiarioUpdate,
    negocio_id: str = Depends(validate_negocio_id),
    current_user: schemas.UsuarioProfile = Depends(get_current_tecnico_user),
    db: firestore.client = Depends(get_db)
):
    """Atualiza um item específico do checklist diário."""
    try:
        # Usar função do CRUD que já implementa a lógica de atualização
        result = crud.atualizar_item_checklist_diario(db, paciente_id, item_id, update_data)
        
        if not result:
            raise HTTPException(
                status_code=404, 
                detail="Item do checklist não encontrado ou já foi concluído por outro técnico"
            )
        
        return result
        
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao atualizar item do checklist: {str(e)}")

# =================================================================================
# ENDPOINTS DO DIÁRIO DO TÉCNICO
# =================================================================================

@router.post("/pacientes/{paciente_id}/diario", response_model=schemas.DiarioTecnicoResponse, status_code=status.HTTP_201_CREATED)
def criar_registro_diario(
    paciente_id: str,
    registro_data: schemas.DiarioTecnicoCreate,
    current_user: schemas.UsuarioProfile = Depends(get_current_tecnico_user),
    db: firestore.client = Depends(get_db)
):
    """Cria um novo registro no diário do técnico."""
    return crud.criar_registro_diario(db, registro_data, current_user)

@router.get("/pacientes/{paciente_id}/diario", response_model=List[schemas.DiarioTecnicoResponse])
def listar_registros_diario(
    paciente_id: str,
    current_user: schemas.UsuarioProfile = Depends(get_current_tecnico_user),
    db: firestore.client = Depends(get_db)
):
    """Lista todos os registros do diário do técnico para um paciente."""
    return crud.listar_registros_diario(db, paciente_id)

# =================================================================================
# ENDPOINTS DE REGISTROS ESTRUTURADOS
# =================================================================================

@router.post("/pacientes/{paciente_id}/registros", response_model=schemas.RegistroDiarioResponse, status_code=status.HTTP_201_CREATED)
def criar_registro_estruturado(
    paciente_id: str,
    registro_data: schemas.RegistroDiarioCreate,
    negocio_id: str = Depends(validate_negocio_id),
    current_user: schemas.UsuarioProfile = Depends(get_current_tecnico_user),
    db: firestore.client = Depends(get_db)
):
    """Cria um novo registro estruturado para um paciente."""
    try:
        # Verificar se o paciente existe e pertence ao negócio
        pacientes = crud.listar_pacientes_por_profissional_ou_tecnico(db, negocio_id, current_user.id, 'tecnico')
        paciente_encontrado = None
        
        for paciente in pacientes:
            if paciente['id'] == paciente_id:
                paciente_encontrado = paciente
                break
        
        if not paciente_encontrado:
            raise HTTPException(
                status_code=404,
                detail="Paciente não encontrado ou você não tem acesso a ele"
            )
        
        # Criar registro
        return crud.criar_registro_diario_estruturado(db, registro_data, current_user.id)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao criar registro: {str(e)}")

@router.get("/pacientes/{paciente_id}/registros", response_model=List[schemas.RegistroDiarioResponse])
def listar_registros_estruturados(
    paciente_id: str,
    negocio_id: str = Depends(validate_negocio_id),
    current_user: schemas.UsuarioProfile = Depends(get_current_tecnico_user),
    db: firestore.client = Depends(get_db)
):
    """Lista todos os registros estruturados de um paciente."""
    try:
        return crud.listar_registros_diario_estruturado(db, paciente_id, negocio_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao listar registros: {str(e)}")

# =================================================================================
# ENDPOINTS DE SUPORTE PSICOLÓGICO
# =================================================================================

@router.get("/pacientes/{paciente_id}/suporte-psicologico", response_model=List[schemas.SuportePsicologicoResponse])
def listar_suporte_psicologico_paciente(
    paciente_id: str,
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """Lista todos os registros de suporte psicológico de um paciente."""
    return crud.listar_suportes_psicologicos(db, paciente_id)

@router.post("/pacientes/{paciente_id}/suporte-psicologico", response_model=schemas.SuportePsicologicoResponse, status_code=status.HTTP_201_CREATED)
def criar_suporte_psicologico_paciente(
    paciente_id: str,
    suporte_data: schemas.SuportePsicologicoCreate,
    current_user: schemas.UsuarioProfile = Depends(get_current_admin_or_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """Cria um novo registro de suporte psicológico para um paciente."""
    return crud.criar_suporte_psicologico(db, paciente_id, suporte_data, current_user.id)

@router.put("/pacientes/{paciente_id}/suporte-psicologico/{suporte_id}", response_model=schemas.SuportePsicologicoResponse)
def atualizar_suporte_psicologico_paciente(
    paciente_id: str,
    suporte_id: str,
    update_data: schemas.SuportePsicologicoUpdate,
    current_user: schemas.UsuarioProfile = Depends(get_current_admin_or_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """Atualiza um registro de suporte psicológico."""
    result = crud.atualizar_suporte_psicologico(db, paciente_id, suporte_id, update_data, current_user.id)
    if not result:
        raise HTTPException(status_code=404, detail="Registro de suporte psicológico não encontrado")
    return result

@router.delete("/pacientes/{paciente_id}/suporte-psicologico/{suporte_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_suporte_psicologico_paciente(
    paciente_id: str,
    suporte_id: str,
    current_user: schemas.UsuarioProfile = Depends(get_current_admin_or_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """Remove um registro de suporte psicológico."""
    success = crud.deletar_suporte_psicologico(db, paciente_id, suporte_id)
    if not success:
        raise HTTPException(status_code=404, detail="Registro de suporte psicológico não encontrado")

# =================================================================================
# ENDPOINTS DE SUPERVISÃO
# =================================================================================

@router.get("/pacientes/{paciente_id}/tecnicos-supervisionados", response_model=List[schemas.TecnicoProfileReduzido])
def listar_tecnicos_supervisionados_por_paciente(
    paciente_id: str,
    negocio_id: str = Depends(validate_negocio_id),
    current_user: schemas.UsuarioProfile = Depends(get_paciente_autorizado),
    db: firestore.client = Depends(get_db)
):
    """Lista os técnicos vinculados a um paciente que estão sob supervisão do usuário."""
    # Obtém a role do usuário
    user_roles = current_user.roles or {}
    user_role = user_roles.get(negocio_id)
    is_admin = user_role == 'admin'
    
    if is_admin:
        # Admin vê todos os técnicos vinculados ao paciente
        paciente_doc = db.collection('usuarios').document(paciente_id).get()
        if not paciente_doc.exists:
            raise HTTPException(status_code=404, detail="Paciente não encontrado")
        
        paciente_data = paciente_doc.to_dict()
        tecnicos_vinculados_ids = paciente_data.get('tecnicos_ids', [])
        
        tecnicos_perfil = []
        for tecnico_id in tecnicos_vinculados_ids:
            tecnico_doc = db.collection('usuarios').document(tecnico_id).get()
            if tecnico_doc.exists:
                tecnico_data = tecnico_doc.to_dict()
                
                # Descriptografar o nome do técnico
                nome_tecnico = tecnico_data.get('nome', 'Nome não disponível')
                if nome_tecnico and nome_tecnico != 'Nome não disponível':
                    try:
                        nome_tecnico = crud.decrypt_data(nome_tecnico)
                    except Exception:
                        nome_tecnico = "[Erro na descriptografia]"
                
                tecnicos_perfil.append(schemas.TecnicoProfileReduzido(
                    id=tecnico_doc.id,
                    nome=nome_tecnico,
                    email=tecnico_data.get('email', 'Email não disponível')
                ))
        return tecnicos_perfil
    else:
        # Para enfermeiros, aplicar lógica de supervisão
        if user_role not in ["profissional", "admin"]:
            raise HTTPException(
                status_code=403,
                detail="Acesso negado: apenas supervisores podem ver técnicos supervisionados"
            )
        
        return crud.listar_tecnicos_supervisionados_por_paciente(db, paciente_id, current_user.id, negocio_id)

@router.get("/pacientes/{paciente_id}/dados-completos", response_model=schemas.UsuarioProfile)
def obter_dados_completos_paciente(
    paciente_id: str,
    current_user: schemas.UsuarioProfile = Depends(get_paciente_autorizado),
    db: firestore.client = Depends(get_db)
):
    """Obtém dados completos de um paciente específico."""
    # Buscar dados do paciente
    paciente_doc = db.collection('usuarios').document(paciente_id).get()
    if not paciente_doc.exists:
        raise HTTPException(status_code=404, detail="Paciente não encontrado")
    
    paciente_data = paciente_doc.to_dict()
    paciente_data['id'] = paciente_doc.id
    
    # Descriptografar dados sensíveis
    paciente_data = crud.decrypt_user_sensitive_fields(paciente_data, ['nome', 'telefone'])
    
    return paciente_data

@router.patch("/diario/{registro_id}", response_model=schemas.DiarioTecnicoResponse)
def atualizar_registro_diario_tecnico(
    registro_id: str,
    update_data: schemas.DiarioTecnicoUpdate,
    current_user: schemas.UsuarioProfile = Depends(get_current_tecnico_user),
    db: firestore.client = Depends(get_db)
):
    """Atualiza um registro específico do diário do técnico."""
    result = crud.atualizar_registro_diario(db, registro_id, update_data, current_user.id)
    if not result:
        raise HTTPException(status_code=404, detail="Registro do diário não encontrado")
    return result