# routers/admin.py
"""
Router para endpoints de administração da plataforma e gestão do negócio
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query, Path
from typing import List
import schemas
import crud
from database import get_db
from auth import (
    get_super_admin_user, get_current_admin_user,
    get_current_admin_or_profissional_user,
    validate_path_negocio_id
)
from firebase_admin import firestore

# Router para Admin - Plataforma
platform_admin_router = APIRouter(prefix="/admin", tags=["Admin - Plataforma"])

@platform_admin_router.post("/negocios", response_model=schemas.NegocioResponse)
def admin_criar_negocio(
    negocio_data: schemas.NegocioCreate,
    admin: schemas.UsuarioProfile = Depends(get_super_admin_user),
    db: firestore.client = Depends(get_db)
):
    """
    (Super-Admin) Cria um novo negócio na plataforma e retorna os dados,
    incluindo o código de convite para o dono do negócio.
    """
    return crud.admin_criar_negocio(db, negocio_data, admin.firebase_uid)

@platform_admin_router.get("/negocios", response_model=List[schemas.NegocioResponse])
def admin_listar_negocios(
    admin: schemas.UsuarioProfile = Depends(get_super_admin_user),
    db: firestore.client = Depends(get_db)
):
    """(Super-Admin) Lista todos os negócios cadastrados na plataforma."""
    return crud.admin_listar_negocios(db)


# Router para Admin - Gestão do Negócio
business_admin_router = APIRouter(prefix="/negocios/{negocio_id}", tags=["Admin - Gestão do Negócio"])

@business_admin_router.get("/usuarios", response_model=List[schemas.UsuarioProfile])
def listar_usuarios_do_negocio(
    negocio_id: str = Depends(validate_path_negocio_id),
    status: str = Query('ativo', description="Filtre por status: 'ativo', 'inativo' ou 'all'."),
    role: str = Query(None, description="Filtre por role: 'admin', 'medico', 'profissional', etc."),
    current_user: schemas.UsuarioProfile = Depends(get_current_admin_or_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """(Admin) Lista todos os usuários de um negócio com filtro de status e role."""
    usuarios = crud.admin_listar_usuarios_por_negocio(db, negocio_id, status)
    
    # Filtrar por role se especificado
    if role:
        usuarios_filtrados = []
        for usuario in usuarios:
            user_roles = usuario.get('roles', {})
            user_role = user_roles.get(negocio_id)
            if user_role == role:
                usuarios_filtrados.append(usuario)
        return usuarios_filtrados
    
    return usuarios

@business_admin_router.get("/clientes", response_model=List[schemas.UsuarioProfile])
def listar_clientes_do_negocio(
    negocio_id: str = Depends(validate_path_negocio_id),
    admin: schemas.UsuarioProfile = Depends(get_current_admin_user),
    db: firestore.client = Depends(get_db)
):
    """(Admin) Lista todos os clientes de um negócio."""
    return crud.admin_listar_clientes_por_negocio(db, negocio_id, 'ativo')

@business_admin_router.patch("/usuarios/{user_id}/status", response_model=schemas.UsuarioProfile)
def alterar_status_usuario(
    user_id: str,
    request: schemas.AlterarStatusRequest,
    negocio_id: str = Depends(validate_path_negocio_id),
    admin: schemas.UsuarioProfile = Depends(get_current_admin_user),
    db: firestore.client = Depends(get_db)
):
    """(Admin) Altera o status de um usuário no negócio."""
    result = crud.admin_set_usuario_status(db, negocio_id, user_id, request.novo_status, admin.firebase_uid)
    if not result:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return result

@business_admin_router.post("/pacientes", response_model=schemas.UsuarioProfile)
def criar_paciente_via_admin(
    paciente_data: schemas.PacienteCreateByAdmin,
    negocio_id: str = Depends(validate_path_negocio_id),
    current_user: schemas.UsuarioProfile = Depends(get_current_admin_or_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """(Admin) Cria um novo paciente via interface administrativa."""
    return crud.admin_criar_paciente(db, negocio_id, paciente_data)

@business_admin_router.patch("/usuarios/{user_id}/role", response_model=schemas.UsuarioProfile)
def alterar_role_usuario(
    user_id: str,
    request: schemas.AlterarRoleRequest,
    negocio_id: str = Depends(validate_path_negocio_id),
    admin: schemas.UsuarioProfile = Depends(get_current_admin_user),
    db: firestore.client = Depends(get_db)
):
    """(Admin) Altera o role de um usuário no negócio."""
    result = crud.admin_atualizar_role_usuario(db, negocio_id, user_id, request.novo_role, admin.firebase_uid)
    if not result:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return result

@business_admin_router.post("/medicos", response_model=schemas.MedicoResponse)
def criar_medico(
    medico_data: schemas.MedicoBase,
    negocio_id: str = Depends(validate_path_negocio_id),
    admin: schemas.UsuarioProfile = Depends(get_current_admin_user),
    db: firestore.client = Depends(get_db)
):
    """(Admin) Cria um novo médico no sistema."""
    return crud.criar_medico(db, medico_data)

@business_admin_router.get("/medicos", response_model=List[schemas.MedicoResponse])
def listar_medicos(
    negocio_id: str = Depends(validate_path_negocio_id),
    admin: schemas.UsuarioProfile = Depends(get_current_admin_user),
    db: firestore.client = Depends(get_db)
):
    """(Admin) Lista todos os médicos do negócio."""
    return crud.listar_medicos_por_negocio(db, negocio_id)

@business_admin_router.patch("/medicos/{medico_id}", response_model=schemas.MedicoResponse)
def atualizar_medico(
    medico_id: str,
    update_data: schemas.MedicoUpdate,
    negocio_id: str = Depends(validate_path_negocio_id),
    admin: schemas.UsuarioProfile = Depends(get_current_admin_user),
    db: firestore.client = Depends(get_db)
):
    """(Admin) Atualiza dados de um médico."""
    result = crud.atualizar_medico(db, medico_id, update_data)
    if not result:
        raise HTTPException(status_code=404, detail="Médico não encontrado")
    return result

@business_admin_router.delete("/medicos/{medico_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_medico(
    medico_id: str,
    negocio_id: str = Depends(validate_path_negocio_id),
    admin: schemas.UsuarioProfile = Depends(get_current_admin_user),
    db: firestore.client = Depends(get_db)
):
    """(Admin) Remove um médico do sistema."""
    success = crud.deletar_medico(db, medico_id)
    if not success:
        raise HTTPException(status_code=404, detail="Médico não encontrado")

@business_admin_router.get("/admin-status")
def verificar_admin_status(
    negocio_id: str = Depends(validate_path_negocio_id),
    db: firestore.client = Depends(get_db)
):
    """Verifica se o negócio já possui um administrador."""
    has_admin = crud.check_admin_status(db, negocio_id)
    return {"has_admin": has_admin}

@business_admin_router.patch("/usuarios/{user_id}/consent", response_model=schemas.UsuarioProfile)
def admin_atualizar_consentimento_lgpd(
    user_id: str,
    consent_data: schemas.ConsentimentoLGPDUpdate,
    negocio_id: str = Depends(validate_path_negocio_id),
    current_user: schemas.UsuarioProfile = Depends(get_current_admin_or_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """(Admin) Atualiza o consentimento LGPD de um usuário."""
    result = crud.atualizar_consentimento_lgpd(db, user_id, consent_data)
    if not result:
        raise HTTPException(status_code=404, detail="Usuário não encontrado ou não foi possível atualizar o consentimento")
    return result

@business_admin_router.post("/vincular-paciente", response_model=schemas.UsuarioProfile)
def vincular_ou_desvincular_paciente(
    vinculo_data: schemas.VinculoCreate,
    negocio_id: str = Depends(validate_path_negocio_id),
    current_user: schemas.UsuarioProfile = Depends(get_current_admin_or_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """(Admin ou Enfermeiro) Vincula um paciente a um enfermeiro ou desvincula ao enviar 'enfermeiro_id' como null."""
    paciente_atualizado = crud.vincular_paciente_enfermeiro(
        db,
        negocio_id=negocio_id,
        paciente_id=vinculo_data.paciente_id,
        enfermeiro_id=vinculo_data.enfermeiro_id,
        autor_uid=current_user.firebase_uid
    )
    if not paciente_atualizado:
        raise HTTPException(status_code=404, detail="Paciente ou enfermeiro não encontrado")
    return paciente_atualizado

@business_admin_router.delete("/vincular-paciente", response_model=schemas.UsuarioProfile)
def desvincular_paciente(
    vinculo_data: schemas.VinculoCreate,
    negocio_id: str = Depends(validate_path_negocio_id),
    admin: schemas.UsuarioProfile = Depends(get_current_admin_user),
    db: firestore.client = Depends(get_db)
):
    """(Admin de Negócio) Desvincula um paciente de seu enfermeiro."""
    paciente_atualizado = crud.desvincular_paciente_enfermeiro(
        db,
        negocio_id=negocio_id,
        paciente_id=vinculo_data.paciente_id,
        autor_uid=admin.firebase_uid
    )
    if not paciente_atualizado:
        raise HTTPException(status_code=404, detail="Paciente não encontrado")
    return paciente_atualizado

@business_admin_router.patch("/pacientes/{paciente_id}/vincular-tecnicos", response_model=schemas.UsuarioProfile)
def vincular_tecnicos_ao_paciente(
    paciente_id: str,
    vinculo_data: schemas.TecnicosVincularRequest,
    negocio_id: str = Depends(validate_path_negocio_id),
    admin: schemas.UsuarioProfile = Depends(get_current_admin_user),
    db: firestore.client = Depends(get_db)
):
    """(Admin de Negócio) Vincula ou atualiza a lista de técnicos associados a um paciente."""
    try:
        paciente_atualizado = crud.vincular_tecnicos_paciente(
            db, paciente_id, vinculo_data.tecnicos_ids, admin.firebase_uid
        )
        if not paciente_atualizado:
            raise HTTPException(status_code=404, detail="Paciente não encontrado")
        return paciente_atualizado
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Ocorreu um erro interno no servidor")

@business_admin_router.post("/pacientes/{paciente_id}/vincular-medico", response_model=schemas.UsuarioProfile)
def vincular_medico_ao_paciente(
    paciente_id: str,
    vinculo_data: schemas.MedicoVincularRequest,
    negocio_id: str = Depends(validate_path_negocio_id),
    admin_or_profissional: schemas.UsuarioProfile = Depends(get_current_admin_or_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """(Admin ou Enfermeiro) Vincula ou desvincula um médico de um paciente."""
    try:
        paciente_atualizado = crud.vincular_paciente_medico(
            db, negocio_id, paciente_id, vinculo_data.medico_id, admin_or_profissional.firebase_uid
        )
        if not paciente_atualizado:
            raise HTTPException(status_code=404, detail="Paciente não encontrado")
        return paciente_atualizado
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Erro inesperado ao vincular médico")

@business_admin_router.patch("/usuarios/{tecnico_id}/vincular-supervisor", response_model=schemas.UsuarioProfile)
def vincular_ou_desvincular_supervisor(
    tecnico_id: str,
    vinculo_data: schemas.SupervisorVincularRequest,
    negocio_id: str = Depends(validate_path_negocio_id),
    admin: schemas.UsuarioProfile = Depends(get_current_admin_user),
    db: firestore.client = Depends(get_db)
):
    """(Admin de Negócio) Vincula um supervisor a um técnico ou desvincula ao enviar 'supervisor_id' como null."""
    try:
        tecnico_atualizado = crud.vincular_supervisor_tecnico(
            db, tecnico_id, vinculo_data.supervisor_id, admin.firebase_uid
        )
        if not tecnico_atualizado:
            raise HTTPException(status_code=404, detail="Técnico ou supervisor não encontrado")
        return tecnico_atualizado
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))