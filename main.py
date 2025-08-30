# barbearia-backend/main.py (Versão estável com Checklist do Técnico)

from fastapi import FastAPI, Depends, HTTPException, status, Header, Path, Query, UploadFile, File
from typing import List, Optional, Union
import schemas, crud
import logging
from datetime import date
from database import initialize_firebase_app, get_db
from auth import (
    get_current_user_firebase, get_super_admin_user, get_current_admin_user, 
    get_current_profissional_user, get_optional_current_user_firebase, 
    validate_negocio_id, validate_path_negocio_id, get_paciente_autorizado, 
    get_current_admin_or_profissional_user, get_current_tecnico_user
)
from firebase_admin import firestore
from pydantic import BaseModel
from google.cloud import storage
from PIL import Image
from io import BytesIO
import os
import uuid
from fastapi.responses import JSONResponse

# --- Modelo para a requisição de promoção ---
class PromoteRequest(BaseModel):
    firebase_uid: str

# --- Configuração da Aplicação ---
app = FastAPI(
    title="API de Agendamento Multi-Tenant",
    description="Backend para múltiplos negócios de agendamento, usando Firebase e Firestore.",
    version="2.2.0" # Versão atualizada com fluxo do técnico
)

# Adicionar um logger para ajudar no debug
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CLOUD_STORAGE_BUCKET_NAME_GLOBAL = os.getenv("CLOUD_STORAGE_BUCKET_NAME")


# --- Evento de Startup ---
@app.on_event("startup")
def startup_event():
    """Inicializa a conexão com o Firebase ao iniciar a aplicação."""
    initialize_firebase_app()

# --- Endpoint Raiz ---
@app.get("/")
def root():
    return {"mensagem": "API de Agendamento Multi-Tenant funcionando", "versao": "2.2.0-FINAL"}

# =================================================================================
# ENDPOINTS DE ADMINISTRAÇÃO DA PLATAFORMA (SUPER-ADMIN)
# =================================================================================

@app.post("/admin/negocios", response_model=schemas.NegocioResponse, tags=["Admin - Plataforma"])
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

@app.get("/admin/negocios", response_model=List[schemas.NegocioResponse], tags=["Admin - Plataforma"])
def admin_listar_negocios(
    admin: schemas.UsuarioProfile = Depends(get_super_admin_user),
    db: firestore.client = Depends(get_db)
):
    """(Super-Admin) Lista todos os negócios cadastrados na plataforma."""
    return crud.admin_listar_negocios(db)

# =================================================================================
# ENDPOINTS DE GERENCIAMENTO DO NEGÓCIO (ADMIN DE NEGÓCIO)
# =================================================================================

@app.get("/negocios/{negocio_id}/usuarios", response_model=List[schemas.UsuarioProfile], tags=["Admin - Gestão do Negócio"])
def listar_usuarios_do_negocio(
    negocio_id: str = Depends(validate_path_negocio_id),
    status: str = Query('ativo', description="Filtre por status: 'ativo' ou 'arquivado'."),
    admin: schemas.UsuarioProfile = Depends(get_current_admin_user),
    db: firestore.client = Depends(get_db)
):
    """(Admin de Negócio) Lista todos os usuários (clientes, técnicos e profissionais) do seu negócio."""
    return crud.admin_listar_usuarios_por_negocio(db, negocio_id, status)

@app.get("/negocios/{negocio_id}/clientes", response_model=List[schemas.UsuarioProfile], tags=["Admin - Gestão do Negócio"])
def listar_clientes_do_negocio(
    negocio_id: str = Depends(validate_path_negocio_id),
    status: str = Query('ativo', description="Filtre por status: 'ativo' ou 'arquivado'."),
    admin: schemas.UsuarioProfile = Depends(get_current_admin_user),
    db: firestore.client = Depends(get_db)
):
    """(Admin de Negócio) Lista todos os usuários com o papel de 'cliente' no seu negócio."""
    return crud.admin_listar_clientes_por_negocio(db, negocio_id, status)

# @app.patch("/negocios/{negocio_id}/pacientes/{paciente_id}/status", response_model=schemas.UsuarioProfile, tags=["Admin - Gestão do Negócio"])
# def set_paciente_status(
#     paciente_id: str,
#     status_update: schemas.StatusUpdateRequest,
#     negocio_id: str = Depends(validate_path_negocio_id),
#     admin: schemas.UsuarioProfile = Depends(get_current_admin_user),
#     db: firestore.client = Depends(get_db)
# ):
#     """(Admin de Negócio) Define o status de um paciente como 'ativo' ou 'arquivado'."""
#     try:
#         paciente_atualizado = crud.admin_set_paciente_status(
#             db, negocio_id, paciente_id, status_update.status, admin.firebase_uid
#         )
#         if not paciente_atualizado:
#             raise HTTPException(status_code=404, detail="Paciente não encontrado.")
#         return paciente_atualizado
#     except ValueError as e:
#         raise HTTPException(status_code=400, detail=str(e))

@app.patch("/negocios/{negocio_id}/usuarios/{user_id}/status", response_model=schemas.UsuarioProfile, tags=["Admin - Gestão do Negócio"])
def set_usuario_status(
    user_id: str,
    status_update: schemas.StatusUpdateRequest,
    negocio_id: str = Depends(validate_path_negocio_id),
    admin: schemas.UsuarioProfile = Depends(get_current_admin_user),
    db: firestore.client = Depends(get_db)
):
    """(Admin de Negócio) Define o status de um usuário como 'ativo' ou 'inativo'."""
    try:
        usuario_atualizado = crud.admin_set_usuario_status(
            db, negocio_id, user_id, status_update.status, admin.firebase_uid
        )
        if not usuario_atualizado:
            raise HTTPException(status_code=404, detail="Usuário não encontrado.")
        return usuario_atualizado
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/negocios/{negocio_id}/pacientes", response_model=schemas.UsuarioProfile, tags=["Admin - Gestão do Negócio"])
def criar_paciente_por_admin(
    paciente_data: schemas.PacienteCreateByAdmin,
    negocio_id: str = Depends(validate_path_negocio_id),
    current_user: schemas.UsuarioProfile = Depends(get_current_admin_or_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """(Admin de Negócio ou Enfermeiro) Cria um novo paciente, registrando-o no sistema."""
    try:
        novo_paciente = crud.admin_criar_paciente(db, negocio_id, paciente_data)
        return novo_paciente
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Erro inesperado ao criar paciente: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ocorreu um erro interno no servidor.")

@app.patch("/negocios/{negocio_id}/usuarios/{user_id}/role", response_model=schemas.UsuarioProfile, tags=["Admin - Gestão do Negócio"])
def atualizar_role_usuario(
    user_id: str,
    role_update: schemas.RoleUpdateRequest,
    negocio_id: str = Depends(validate_path_negocio_id),
    admin: schemas.UsuarioProfile = Depends(get_current_admin_user),
    db: firestore.client = Depends(get_db)
):
    """(Admin de Negócio) Atualiza o papel de um usuário (para 'cliente', 'profissional', 'tecnico', etc.)."""
    try:
        usuario_atualizado = crud.admin_atualizar_role_usuario(
            db, negocio_id, user_id, role_update.role, admin.firebase_uid
        )
        if not usuario_atualizado:
            raise HTTPException(status_code=404, detail="Usuário não encontrado ou não pertence a este negócio.")
        return usuario_atualizado
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/negocios/{negocio_id}/medicos", response_model=schemas.MedicoResponse, tags=["Admin - Gestão do Negócio"])
def criar_medico(
    medico_data: schemas.MedicoBase,
    negocio_id: str = Depends(validate_path_negocio_id),
    admin: schemas.UsuarioProfile = Depends(get_current_admin_user),
    db: firestore.client = Depends(get_db)
):
    """(Admin de Negócio) Cadastra um novo médico de referência para a clínica."""
    medico_data.negocio_id = negocio_id
    return crud.criar_medico(db, medico_data)

@app.get("/negocios/{negocio_id}/medicos", response_model=List[schemas.MedicoResponse], tags=["Admin - Gestão do Negócio"])
def listar_medicos(
    negocio_id: str = Depends(validate_path_negocio_id),
    admin: schemas.UsuarioProfile = Depends(get_current_admin_user),
    db: firestore.client = Depends(get_db)
):
    """(Admin de Negócio) Lista todos os médicos de referência da clínica."""
    return crud.listar_medicos_por_negocio(db, negocio_id)

@app.patch("/negocios/{negocio_id}/medicos/{medico_id}", response_model=schemas.MedicoResponse, tags=["Admin - Gestão do Negócio"])
def update_medico_endpoint(
    medico_id: str,
    update_data: schemas.MedicoUpdate,
    negocio_id: str = Depends(validate_path_negocio_id),
    admin: schemas.UsuarioProfile = Depends(get_current_admin_user),
    db: firestore.client = Depends(get_db)
):
    """(Admin de Negócio) Atualiza os dados de um médico de referência."""
    medico_atualizado = crud.update_medico(db, negocio_id, medico_id, update_data)
    if not medico_atualizado:
        raise HTTPException(status_code=404, detail="Médico não encontrado ou não pertence a este negócio.")
    return medico_atualizado

@app.delete("/negocios/{negocio_id}/medicos/{medico_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Admin - Gestão do Negócio"])
def delete_medico_endpoint(
    medico_id: str,
    negocio_id: str = Depends(validate_path_negocio_id),
    admin: schemas.UsuarioProfile = Depends(get_current_admin_user),
    db: firestore.client = Depends(get_db)
):
    """(Admin de Negócio) Deleta um médico de referência."""
    if not crud.delete_medico(db, negocio_id, medico_id):
        raise HTTPException(status_code=404, detail="Médico não encontrado ou não pertence a este negócio.")
    return

# @app.post("/negocios/{negocio_id}/vincular-paciente", response_model=schemas.UsuarioProfile, tags=["Admin - Gestão do Negócio"])
# def vincular_paciente(
#     vinculo_data: schemas.VinculoCreate,
#     negocio_id: str = Depends(validate_path_negocio_id),
#     current_user: schemas.UsuarioProfile = Depends(get_current_admin_or_profissional_user),
#     db: firestore.client = Depends(get_db)
# ):
#     """(Admin de Negócio ou Enfermeiro) Vincula um paciente a um enfermeiro."""
#     paciente_atualizado = crud.vincular_paciente_enfermeiro(
#         db,
#         negocio_id=negocio_id,
#         paciente_id=vinculo_data.paciente_id,
#         enfermeiro_id=vinculo_data.enfermeiro_id,
#         autor_uid=current_user.firebase_uid
#     )
#     if not paciente_atualizado:
#         raise HTTPException(status_code=404, detail="Paciente ou enfermeiro não encontrado.")
#     return paciente_atualizado

@app.post("/negocios/{negocio_id}/vincular-paciente", response_model=schemas.UsuarioProfile, tags=["Admin - Gestão do Negócio"])
def vincular_ou_desvincular_paciente( # Nome alterado para clareza
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
        enfermeiro_id=vinculo_data.enfermeiro_id, # pode ser null
        autor_uid=current_user.firebase_uid
    )
    if not paciente_atualizado:
        raise HTTPException(status_code=404, detail="Paciente ou enfermeiro não encontrado.")
    return paciente_atualizado

@app.delete("/negocios/{negocio_id}/vincular-paciente", response_model=schemas.UsuarioProfile, tags=["Admin - Gestão do Negócio"])
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
        raise HTTPException(status_code=404, detail="Paciente não encontrado.")
    return paciente_atualizado

@app.patch("/negocios/{negocio_id}/pacientes/{paciente_id}/vincular-tecnicos", response_model=schemas.UsuarioProfile, tags=["Admin - Gestão do Negócio"])
def vincular_tecnicos_ao_paciente(
    negocio_id: str = Depends(validate_path_negocio_id),
    paciente_id: str = Path(..., description="ID do paciente a ser modificado."),
    vinculo_data: schemas.TecnicosVincularRequest = ...,
    admin: schemas.UsuarioProfile = Depends(get_current_admin_user),
    db: firestore.client = Depends(get_db)
):
    """(Admin de Negócio) Vincula ou atualiza a lista de técnicos associados a um paciente."""
    try:
        paciente_atualizado = crud.vincular_tecnicos_paciente(
            db, paciente_id, vinculo_data.tecnicos_ids, admin.firebase_uid
        )
        if not paciente_atualizado:
            raise HTTPException(status_code=404, detail="Paciente não encontrado.")
        return paciente_atualizado
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Erro inesperado ao vincular técnicos: {e}")
        raise HTTPException(status_code=500, detail="Ocorreu um erro interno no servidor.")

# @app.patch("/negocios/{negocio_id}/usuarios/{tecnico_id}/vincular-supervisor", response_model=schemas.UsuarioProfile, tags=["Admin - Gestão do Negócio"])
# def vincular_supervisor_ao_tecnico(
#     negocio_id: str = Depends(validate_path_negocio_id),
#     tecnico_id: str = Path(..., description="ID do usuário (documento) do técnico a ser modificado."),
#     vinculo_data: schemas.SupervisorVincularRequest = ...,
#     admin: schemas.UsuarioProfile = Depends(get_current_admin_user),
#     db: firestore.client = Depends(get_db)
# ):
#     """(Admin de Negócio) Vincula um enfermeiro supervisor a um técnico."""
#     try:
#         tecnico_atualizado = crud.vincular_supervisor_tecnico(
#             db, tecnico_id, vinculo_data.supervisor_id, admin.firebase_uid
#         )
#         if not tecnico_atualizado:
#             raise HTTPException(status_code=404, detail="Técnico ou supervisor não encontrado.")
#         return tecnico_atualizado
#     except ValueError as e:
#         raise HTTPException(status_code=400, detail=str(e))
#     except Exception as e:
#         logger.error(f"Erro inesperado ao vincular supervisor: {e}")
#         raise HTTPException(status_code=500, detail="Ocorreu um erro interno no servidor.")

@app.patch("/negocios/{negocio_id}/usuarios/{tecnico_id}/vincular-supervisor", response_model=schemas.UsuarioProfile, tags=["Admin - Gestão do Negócio"])
def vincular_ou_desvincular_supervisor( # Nome alterado para clareza
    negocio_id: str = Depends(validate_path_negocio_id),
    tecnico_id: str = Path(..., description="ID do usuário (documento) do técnico."),
    vinculo_data: schemas.SupervisorVincularRequest = ...,
    admin: schemas.UsuarioProfile = Depends(get_current_admin_user),
    db: firestore.client = Depends(get_db)
):
    """(Admin de Negócio) Vincula um supervisor a um técnico ou desvincula ao enviar 'supervisor_id' como null."""
    try:
        tecnico_atualizado = crud.vincular_supervisor_tecnico(
            db, tecnico_id, vinculo_data.supervisor_id, admin.firebase_uid # pode ser null
        )
        if not tecnico_atualizado:
            raise HTTPException(status_code=404, detail="Técnico ou supervisor não encontrado.")
        return tecnico_atualizado
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =================================================================================
# ENDPOINTS DA FICHA DO PACIENTE (Módulo Clínico)
# =================================================================================

@app.post("/pacientes/{paciente_id}/consultas", response_model=schemas.ConsultaResponse, status_code=status.HTTP_201_CREATED, tags=["Ficha do Paciente"])
def adicionar_consulta(
    paciente_id: str,
    consulta_data: schemas.ConsultaCreate,
    current_user: schemas.UsuarioProfile = Depends(get_paciente_autorizado),
    db: firestore.client = Depends(get_db)
):
    """(Autorizado) Adiciona uma nova consulta à ficha do paciente."""
    consulta_data.paciente_id = paciente_id
    return crud.criar_consulta(db, consulta_data)

@app.post("/pacientes/{paciente_id}/exames", response_model=schemas.ExameResponse, status_code=status.HTTP_201_CREATED, tags=["Ficha do Paciente"])
def adicionar_exame(
    paciente_id: str,
    exame_data: schemas.ExameCreate,
    current_user: schemas.UsuarioProfile = Depends(get_paciente_autorizado),
    db: firestore.client = Depends(get_db)
):
    """(Autorizado) Adiciona um novo exame à ficha do paciente."""
    exame_data.paciente_id = paciente_id
    consulta_id = exame_data.consulta_id
    return crud.adicionar_exame(db, exame_data, consulta_id)

@app.post("/pacientes/{paciente_id}/medicacoes", response_model=schemas.MedicacaoResponse, status_code=status.HTTP_201_CREATED, tags=["Ficha do Paciente"])
def adicionar_medicacao(
    paciente_id: str,
    medicacao_data: schemas.MedicacaoCreate,
    current_user: schemas.UsuarioProfile = Depends(get_paciente_autorizado),
    db: firestore.client = Depends(get_db)
):
    """(Autorizado) Adiciona uma nova medicação à ficha do paciente."""
    medicacao_data.paciente_id = paciente_id
    consulta_id = medicacao_data.consulta_id
    return crud.prescrever_medicacao(db, medicacao_data, consulta_id)

@app.post("/pacientes/{paciente_id}/checklist-itens", response_model=schemas.ChecklistItemResponse, status_code=status.HTTP_201_CREATED, tags=["Ficha do Paciente"])
def adicionar_checklist_item(
    paciente_id: str,
    item_data: schemas.ChecklistItemCreate,
    current_user: schemas.UsuarioProfile = Depends(get_paciente_autorizado),
    db: firestore.client = Depends(get_db)
):
    """(Autorizado) Adiciona um novo item ao checklist do paciente."""
    item_data.paciente_id = paciente_id
    consulta_id = item_data.consulta_id
    return crud.adicionar_item_checklist(db, item_data, consulta_id)

@app.post("/pacientes/{paciente_id}/orientacoes", response_model=schemas.OrientacaoResponse, status_code=status.HTTP_201_CREATED, tags=["Ficha do Paciente"])
def adicionar_orientacao(
    paciente_id: str,
    orientacao_data: schemas.OrientacaoCreate,
    current_user: schemas.UsuarioProfile = Depends(get_paciente_autorizado),
    db: firestore.client = Depends(get_db)
):
    """(Autorizado) Adiciona uma nova orientação à ficha do paciente."""
    orientacao_data.paciente_id = paciente_id
    consulta_id = orientacao_data.consulta_id
    return crud.criar_orientacao(db, orientacao_data, consulta_id)

@app.get("/pacientes/{paciente_id}/ficha-completa", response_model=schemas.FichaCompletaResponse, tags=["Ficha do Paciente"])
def get_ficha_completa(
    paciente_id: str,
    consulta_id: Optional[str] = Query(None, description="Opcional: força o retorno da consulta informada."),
    current_user: schemas.UsuarioProfile = Depends(get_paciente_autorizado),
    db: firestore.client = Depends(get_db)
):
    """(Autorizado) Retorna a ficha clínica completa do paciente."""
    if consulta_id:
        return {
            "consultas": crud.listar_consultas(db, paciente_id),
            "exames": crud.listar_exames(db, paciente_id, consulta_id),
            "medicacoes": crud.listar_medicacoes(db, paciente_id, consulta_id),
            "checklist": crud._dedup_checklist_items(crud.listar_checklist(db, paciente_id, consulta_id)),
            "orientacoes": crud.listar_orientacoes(db, paciente_id, consulta_id),
        }
    return crud.get_ficha_completa_paciente(db, paciente_id)

@app.get("/pacientes/{paciente_id}/consultas", response_model=List[schemas.ConsultaResponse], tags=["Ficha do Paciente"])
def get_consultas(
    paciente_id: str,
    current_user: schemas.UsuarioProfile = Depends(get_paciente_autorizado),
    db: firestore.client = Depends(get_db)
):
    """(Autorizado) Lista as consultas da ficha do paciente."""
    return crud.listar_consultas(db, paciente_id)

@app.get("/pacientes/{paciente_id}/exames", response_model=List[schemas.ExameResponse], tags=["Ficha do Paciente"])
def get_exames(
    paciente_id: str,
    consulta_id: Optional[str] = Query(None, description="Filtre os exames por um ID de consulta específico."),
    current_user: schemas.UsuarioProfile = Depends(get_paciente_autorizado),
    db: firestore.client = Depends(get_db)
):
    """(Autorizado) Lista os exames da ficha do paciente."""
    return crud.listar_exames(db, paciente_id, consulta_id)

@app.get("/pacientes/{paciente_id}/medicacoes", response_model=List[schemas.MedicacaoResponse], tags=["Ficha do Paciente"])
def get_medicacoes(
    paciente_id: str,
    consulta_id: Optional[str] = Query(None, description="Filtre as medicações por um ID de consulta específico."),
    current_user: schemas.UsuarioProfile = Depends(get_paciente_autorizado),
    db: firestore.client = Depends(get_db)
):
    """(Autorizado) Lista as medicações da ficha do paciente."""
    return crud.listar_medicacoes(db, paciente_id, consulta_id)

@app.get("/pacientes/{paciente_id}/checklist-itens", response_model=List[schemas.ChecklistItemResponse], tags=["Ficha do Paciente"])
def get_checklist_itens(
    paciente_id: str,
    consulta_id: Optional[str] = Query(None, description="Filtre os itens do checklist por um ID de consulta específico."),
    current_user: schemas.UsuarioProfile = Depends(get_paciente_autorizado),
    db: firestore.client = Depends(get_db)
):
    """(Autorizado) Lista os itens do checklist da ficha do paciente."""
    return crud.listar_checklist(db, paciente_id, consulta_id)

@app.get("/pacientes/{paciente_id}/orientacoes", response_model=List[schemas.OrientacaoResponse], tags=["Ficha do Paciente"])
def get_orientacoes(
    paciente_id: str,
    consulta_id: Optional[str] = Query(None, description="Filtre as orientações por um ID de consulta específico."),
    current_user: schemas.UsuarioProfile = Depends(get_paciente_autorizado),
    db: firestore.client = Depends(get_db)
):
    """(Autorizado) Lista as orientações da ficha do paciente."""
    return crud.listar_orientacoes(db, paciente_id, consulta_id)

@app.patch("/pacientes/{paciente_id}/consultas/{consulta_id}", response_model=schemas.ConsultaResponse, tags=["Ficha do Paciente"])
def update_consulta(
    paciente_id: str,
    consulta_id: str,
    update_data: schemas.ConsultaUpdate,
    current_user: schemas.UsuarioProfile = Depends(get_paciente_autorizado),
    db: firestore.client = Depends(get_db)
):
    """(Autorizado) Atualiza uma consulta na ficha do paciente."""
    consulta_atualizada = crud.update_consulta(db, paciente_id, consulta_id, update_data)
    if not consulta_atualizada:
        raise HTTPException(status_code=404, detail="Consulta não encontrada.")
    return consulta_atualizada

@app.delete("/pacientes/{paciente_id}/consultas/{consulta_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Ficha do Paciente"])
def delete_consulta(
    paciente_id: str,
    consulta_id: str,
    current_user: schemas.UsuarioProfile = Depends(get_paciente_autorizado),
    db: firestore.client = Depends(get_db)
):
    """(Autorizado) Deleta uma consulta da ficha do paciente."""
    if not crud.delete_consulta(db, paciente_id, consulta_id):
        raise HTTPException(status_code=404, detail="Consulta não encontrada.")
    return

@app.patch("/pacientes/{paciente_id}/exames/{exame_id}", response_model=schemas.ExameResponse, tags=["Ficha do Paciente"])
def update_exame(
    paciente_id: str,
    exame_id: str,
    update_data: schemas.ExameUpdate,
    current_user: schemas.UsuarioProfile = Depends(get_paciente_autorizado),
    db: firestore.client = Depends(get_db)
):
    """(Autorizado) Atualiza um exame na ficha do paciente."""
    exame_atualizado = crud.update_exame(db, paciente_id, exame_id, update_data)
    if not exame_atualizado:
        raise HTTPException(status_code=404, detail="Exame não encontrado.")
    return exame_atualizado

@app.delete("/pacientes/{paciente_id}/exames/{exame_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Ficha do Paciente"])
def delete_exame(
    paciente_id: str,
    exame_id: str,
    current_user: schemas.UsuarioProfile = Depends(get_paciente_autorizado),
    db: firestore.client = Depends(get_db)
):
    """(Autorizado) Deleta um exame da ficha do paciente."""
    if not crud.delete_exame(db, paciente_id, exame_id):
        raise HTTPException(status_code=404, detail="Exame não encontrada.")
    return

@app.patch("/pacientes/{paciente_id}/medicacoes/{medicacao_id}", response_model=schemas.MedicacaoResponse, tags=["Ficha do Paciente"])
def update_medicacao(
    paciente_id: str,
    medicacao_id: str,
    update_data: schemas.MedicacaoUpdate,
    current_user: schemas.UsuarioProfile = Depends(get_paciente_autorizado),
    db: firestore.client = Depends(get_db)
):
    """(Autorizado) Atualiza uma medicação na ficha do paciente."""
    medicacao_atualizada = crud.update_medicacao(db, paciente_id, medicacao_id, update_data)
    if not medicacao_atualizada:
        raise HTTPException(status_code=404, detail="Medicação não encontrada.")
    return medicacao_atualizada

@app.delete("/pacientes/{paciente_id}/medicacoes/{medicacao_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Ficha do Paciente"])
def delete_medicacao(
    paciente_id: str,
    medicacao_id: str,
    current_user: schemas.UsuarioProfile = Depends(get_paciente_autorizado),
    db: firestore.client = Depends(get_db)
):
    """(Autorizado) Deleta uma medicação da ficha do paciente."""
    if not crud.delete_medicacao(db, paciente_id, medicacao_id):
        raise HTTPException(status_code=404, detail="Medicação não encontrada.")
    return

@app.patch("/pacientes/{paciente_id}/checklist-itens/{item_id}", response_model=schemas.ChecklistItemResponse, tags=["Ficha do Paciente"])
def update_checklist_item(
    paciente_id: str,
    item_id: str,
    update_data: schemas.ChecklistItemUpdate,
    current_user: schemas.UsuarioProfile = Depends(get_paciente_autorizado),
    db: firestore.client = Depends(get_db)
):
    """(Autorizado) Atualiza um item do checklist na ficha do paciente."""
    item_atualizado = crud.update_checklist_item(db, paciente_id, item_id, update_data)
    if not item_atualizado:
        raise HTTPException(status_code=404, detail="Item do checklist não encontrado.")
    return item_atualizado

@app.delete("/pacientes/{paciente_id}/checklist-itens/{item_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Ficha do Paciente"])
def delete_checklist_item(
    paciente_id: str,
    item_id: str,
    current_user: schemas.UsuarioProfile = Depends(get_paciente_autorizado),
    db: firestore.client = Depends(get_db)
):
    """(Autorizado) Deleta um item do checklist da ficha do paciente."""
    if not crud.delete_checklist_item(db, paciente_id, item_id):
        raise HTTPException(status_code=404, detail="Item do checklist não encontrado.")
    return

@app.patch("/pacientes/{paciente_id}/orientacoes/{orientacao_id}", response_model=schemas.OrientacaoResponse, tags=["Ficha do Paciente"])
def update_orientacao(
    paciente_id: str,
    orientacao_id: str,
    update_data: schemas.OrientacaoUpdate,
    current_user: schemas.UsuarioProfile = Depends(get_paciente_autorizado),
    db: firestore.client = Depends(get_db)
):
    """(Autorizado) Atualiza uma orientação na ficha do paciente."""
    orientacao_atualizada = crud.update_orientacao(db, paciente_id, orientacao_id, update_data)
    if not orientacao_atualizada:
        raise HTTPException(status_code=404, detail="Orientação não encontrada.")
    return orientacao_atualizada

@app.delete("/pacientes/{paciente_id}/orientacoes/{orientacao_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Ficha do Paciente"])
def delete_orientacao(
    paciente_id: str,
    orientacao_id: str,
    current_user: schemas.UsuarioProfile = Depends(get_paciente_autorizado),
    db: firestore.client = Depends(get_db)
):
    """(Autorizado) Deleta uma orientação da ficha do paciente."""
    if not crud.delete_orientacao(db, paciente_id, orientacao_id):
        raise HTTPException(status_code=404, detail="Orientação não encontrada.")
    return

# =================================================================================
# ENDPOINTS DO DIÁRIO DO TÉCNICO
# =================================================================================

@app.post("/pacientes/{paciente_id}/diario", response_model=schemas.DiarioTecnicoResponse, status_code=status.HTTP_201_CREATED, tags=["Diário do Técnico"])
def criar_registro_diario(
    paciente_id: str,
    registro_data: schemas.DiarioTecnicoCreate,
    tecnico: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """(Técnico) Adiciona um novo registro de acompanhamento ao diário do paciente."""
    if registro_data.negocio_id not in tecnico.roles or tecnico.roles.get(registro_data.negocio_id) != 'tecnico':
        raise HTTPException(status_code=403, detail="Acesso negado: você não é um técnico deste negócio.")
    
    registro_data.paciente_id = paciente_id
    return crud.criar_registro_diario(db, registro_data, tecnico)

@app.get("/pacientes/{paciente_id}/diario", response_model=List[schemas.DiarioTecnicoResponse], tags=["Diário do Técnico"])
def listar_registros_diario(
    paciente_id: str,
    current_user: schemas.UsuarioProfile = Depends(get_paciente_autorizado),
    db: firestore.client = Depends(get_db)
):
    """(Clínico Autorizado) Lista os registros de acompanhamento do diário do paciente, incluindo dados do técnico."""
    return crud.listar_registros_diario(db, paciente_id)

@app.patch("/pacientes/{paciente_id}/diario/{registro_id}", response_model=schemas.DiarioTecnicoResponse, tags=["Diário do Técnico"])
def update_registro_diario(
    paciente_id: str,
    registro_id: str,
    update_data: schemas.DiarioTecnicoUpdate,
    tecnico: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """(Técnico) Atualiza um de seus registros de acompanhamento."""
    try:
        registro_atualizado = crud.update_registro_diario(db, paciente_id, registro_id, update_data, tecnico.id)
        if not registro_atualizado:
            raise HTTPException(status_code=404, detail="Registro não encontrado.")
        return registro_atualizado
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Erro inesperado ao atualizar registro do diário: {e}")
        raise HTTPException(status_code=500, detail="Ocorreu um erro interno.")

@app.delete("/pacientes/{paciente_id}/diario/{registro_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Diário do Técnico"])
def delete_registro_diario(
    paciente_id: str,
    registro_id: str,
    tecnico: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """(Técnico) Deleta um de seus registros de acompanhamento."""
    try:
        if not crud.delete_registro_diario(db, paciente_id, registro_id, tecnico.id):
            raise HTTPException(status_code=404, detail="Registro não encontrado.")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Erro inesperado ao deletar registro do diário: {e}")
        raise HTTPException(status_code=500, detail="Ocorreu um erro interno.")
    return


# =================================================================================
# ENDPOINTS DE REGISTROS DIÁRIOS ESTRUTURADOS
# =================================================================================

@app.post("/pacientes/{paciente_id}/registros", response_model=schemas.RegistroDiarioResponse, status_code=status.HTTP_201_CREATED, tags=["Registros Estruturados"])
def criar_registro_diario_estruturado_endpoint(
    paciente_id: str,
    registro_data: schemas.RegistroDiarioCreate,
    current_user: schemas.UsuarioProfile = Depends(get_current_tecnico_user),
    db: firestore.client = Depends(get_db)
):
    """(Técnico) Adiciona um novo registro estruturado ao diário de acompanhamento."""
    # O paciente_id já é esperado no corpo da requisição conforme o schema corrigido.
    if registro_data.paciente_id != paciente_id:
        raise HTTPException(status_code=400, detail="ID do paciente na URL e no corpo da requisição não correspondem.")

    try:
        novo_registro = crud.criar_registro_diario_estruturado(db, registro_data, current_user.id)
        return novo_registro
    except Exception as e:
        logger.error(f"Erro inesperado ao criar registro diário estruturado: {e}")
        raise HTTPException(status_code=500, detail="Ocorreu um erro interno no servidor.")

@app.get("/pacientes/{paciente_id}/registros", response_model=List[schemas.RegistroDiarioResponse], tags=["Registros Estruturados"])
def listar_registros_diario_estruturado_endpoint(
    paciente_id: str,
    data: Optional[date] = Query(None, description="Data para filtrar os registros (formato: AAAA-MM-DD)."),
    tipo: Optional[str] = Query(None, description="Tipo de registro para filtrar."),
    current_user: schemas.UsuarioProfile = Depends(get_paciente_autorizado),
    db: firestore.client = Depends(get_db)
):
    """(Clínico Autorizado) Lista registros diários estruturados de um paciente com filtros opcionais."""
    return crud.listar_registros_diario_estruturado(db, paciente_id, data=data, tipo=tipo)

@app.patch("/pacientes/{paciente_id}/registros/{registro_id}", response_model=schemas.RegistroDiarioResponse, tags=["Registros Estruturados"])
def atualizar_registro_diario_estruturado_endpoint(
    paciente_id: str,
    registro_id: str,
    update_data: schemas.RegistroDiarioCreate,
    current_user: schemas.UsuarioProfile = Depends(get_current_tecnico_user),
    db: firestore.client = Depends(get_db)
):
    """(Técnico) Atualiza um de seus registros diários estruturados."""
    try:
        registro_atualizado = crud.atualizar_registro_diario_estruturado(db, paciente_id, registro_id, update_data, current_user.id)
        if not registro_atualizado:
            raise HTTPException(status_code=404, detail="Registro não encontrado.")
        return registro_atualizado
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Erro inesperado ao atualizar registro estruturado: {e}")
        raise HTTPException(status_code=500, detail="Ocorreu um erro interno.")

@app.delete("/pacientes/{paciente_id}/registros/{registro_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Registros Estruturados"])
def deletar_registro_diario_estruturado_endpoint(
    paciente_id: str,
    registro_id: str,
    current_user: schemas.UsuarioProfile = Depends(get_current_tecnico_user),
    db: firestore.client = Depends(get_db)
):
    """(Técnico) Deleta um de seus registros diários estruturados."""
    try:
        if not crud.deletar_registro_diario_estruturado(db, paciente_id, registro_id, current_user.id):
            raise HTTPException(status_code=404, detail="Registro não encontrado.")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Erro inesperado ao deletar registro estruturado: {e}")
        raise HTTPException(status_code=500, detail="Ocorreu um erro interno.")

# =================================================================================
# ENDPOINTS DE SUPERVISÃO
# =================================================================================

@app.get("/pacientes/{paciente_id}/tecnicos-supervisionados", response_model=List[schemas.TecnicoProfileReduzido], tags=["Supervisão"])
def listar_tecnicos_supervisionados_por_paciente_endpoint(
    paciente_id: str,
    negocio_id: str = Header(..., alias="negocio-id"),
    current_user: schemas.UsuarioProfile = Depends(get_paciente_autorizado),
    db: firestore.client = Depends(get_db)
):
    """
    (Gestor ou Enfermeiro) Lista os técnicos vinculados a um paciente
    que estão sob a supervisão do enfermeiro logado.
    Para gestores, lista todos os técnicos vinculados ao paciente.
    """
    
    # Obtém a role do usuário a partir do dicionário roles, usando o negocio_id do Header.
    user_role = current_user.roles.get(negocio_id)
    is_admin = user_role == 'admin'
    
    if is_admin:
        # Lógica para admin ver todos os técnicos vinculados ao paciente
        paciente_doc = db.collection('usuarios').document(paciente_id).get()
        if not paciente_doc.exists:
            raise HTTPException(status_code=404, detail="Paciente não encontrado.")
        
        paciente_data = paciente_doc.to_dict()
        tecnicos_vinculados_ids = paciente_data.get('tecnicos_ids', [])
        
        tecnicos_perfil = []
        for tecnico_id in tecnicos_vinculados_ids:
            tecnico_doc = db.collection('usuarios').document(tecnico_id).get()
            if tecnico_doc.exists:
                tecnico_data = tecnico_doc.to_dict()
                tecnicos_perfil.append(schemas.TecnicoProfileReduzido(
                    id=tecnico_doc.id,
                    nome=tecnico_data.get('nome', 'Nome não disponível'),
                    email=tecnico_data.get('email', 'Email não disponível')
                ))
        return tecnicos_perfil
    else:
        # Se não é admin, é um enfermeiro, então aplicamos a lógica de supervisão
        if user_role not in ["profissional", "admin"]:
             raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acesso negado: esta operação é apenas para Gestores ou Enfermeiros."
            )
        
        # O ID do enfermeiro é o ID do documento do usuário logado
        enfermeiro_id = current_user.id
        return crud.listar_tecnicos_supervisionados_por_paciente(db, paciente_id, enfermeiro_id)
    
# =================================================================================
# ENDPOINTS DE AUTOGESTÃO DO PROFISSIONAL
# =================================================================================

@app.get("/me/profissional", response_model=schemas.ProfissionalResponse, tags=["Profissional - Autogestão"])
def get_meu_perfil_profissional(
    negocio_id: str = Depends(validate_negocio_id),
    profissional_user: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """(Profissional) Retorna o seu próprio perfil profissional."""
    perfil = crud.buscar_profissional_por_uid(db, negocio_id, profissional_user.firebase_uid)
    if not perfil:
        raise HTTPException(status_code=404, detail="Perfil profissional não encontrado para este usuário neste negócio.")
    return perfil

@app.put("/me/profissional", response_model=schemas.ProfissionalResponse, tags=["Profissional - Autogestão"])
def update_meu_perfil_profissional(
    update_data: schemas.ProfissionalUpdate,
    negocio_id: str = Depends(validate_negocio_id),
    profissional_user: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """(Profissional) Atualiza o seu próprio perfil profissional."""
    perfil_atual = crud.buscar_profissional_por_uid(db, negocio_id, profissional_user.firebase_uid)
    if not perfil_atual:
        raise HTTPException(status_code=404, detail="Perfil profissional não encontrado para este usuário neste negócio.")
    
    perfil_atualizado = crud.atualizar_perfil_profissional(db, perfil_atual['id'], update_data)
    return perfil_atualizado

@app.post("/me/servicos", response_model=schemas.ServicoResponse, status_code=status.HTTP_201_CREATED, tags=["Profissional - Autogestão"])
def criar_meu_servico(
    servico_data: schemas.ServicoCreate,
    negocio_id: str = Depends(validate_negocio_id),
    profissional_user: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """(Profissional) Cria um novo serviço associado ao seu perfil."""
    perfil_profissional = crud.buscar_profissional_por_uid(db, negocio_id, profissional_user.firebase_uid)
    if not perfil_profissional:
        raise HTTPException(status_code=404, detail="Perfil profissional não encontrado.")

    servico_data.profissional_id = perfil_profissional['id']
    servico_data.negocio_id = negocio_id
    
    return crud.criar_servico(db, servico_data)

@app.get("/me/servicos", response_model=List[schemas.ServicoResponse], tags=["Profissional - Autogestão"])
def listar_meus_servicos(
    negocio_id: str = Depends(validate_negocio_id),
    profissional_user: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """(Profissional) Lista todos os serviços associados ao seu perfil."""
    perfil_profissional = crud.buscar_profissional_por_uid(db, negocio_id, profissional_user.firebase_uid)
    if not perfil_profissional:
        raise HTTPException(status_code=404, detail="Perfil profissional não encontrado.")
        
    return crud.listar_servicos_por_profissional(db, perfil_profissional['id'])

@app.put("/me/servicos/{servico_id}", response_model=schemas.ServicoResponse, tags=["Profissional - Autogestão"])
def atualizar_meu_servico(
    servico_id: str,
    update_data: schemas.ServicoUpdate,
    negocio_id: str = Depends(validate_negocio_id),
    profissional_user: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """(Profissional) Atualiza um de seus serviços."""
    perfil_atual = crud.buscar_profissional_por_uid(db, negocio_id, profissional_user.firebase_uid)
    if not perfil_atual:
        raise HTTPException(status_code=404, detail="Perfil profissional não encontrado.")
    
    servico_atualizado = crud.atualizar_servico(db, servico_id, perfil_atual['id'], update_data)
    if not servico_atualizado:
        raise HTTPException(status_code=403, detail="Serviço não encontrado ou não pertence a este profissional.")
        
    return servico_atualizado

@app.delete("/me/servicos/{servico_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Profissional - Autogestão"])
def deletar_meu_servico(
    servico_id: str,
    negocio_id: str = Depends(validate_negocio_id),
    profissional_user: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """(Profissional) Deleta um de seus serviços."""
    perfil_profissional = crud.buscar_profissional_por_uid(db, negocio_id, profissional_user.firebase_uid)
    if not perfil_profissional:
        raise HTTPException(status_code=404, detail="Perfil profissional não encontrado.")
        
    if not crud.deletar_servico(db, servico_id, perfil_profissional['id']):
        raise HTTPException(status_code=403, detail="Serviço não encontrado ou não pertence a este profissional.")
    
    return

@app.post("/me/horarios-trabalho", response_model=List[schemas.HorarioTrabalho], tags=["Profissional - Autogestão"])
def definir_meus_horarios(
    horarios: List[schemas.HorarioTrabalho],
    negocio_id: str = Depends(validate_negocio_id),
    profissional_user: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """(Profissional) Define sua grade de horários de trabalho semanal."""
    perfil_profissional = crud.buscar_profissional_por_uid(db, negocio_id, profissional_user.firebase_uid)
    if not perfil_profissional:
        raise HTTPException(status_code=404, detail="Perfil profissional não encontrado.")

    return crud.definir_horarios_trabalho(db, perfil_profissional['id'], horarios)

@app.get("/me/horarios-trabalho", response_model=List[schemas.HorarioTrabalho], tags=["Profissional - Autogestão"])
def get_meus_horarios(
    negocio_id: str = Depends(validate_negocio_id),
    profissional_user: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """(Profissional) Lista sua grade de horários de trabalho."""
    perfil_profissional = crud.buscar_profissional_por_uid(db, negocio_id, profissional_user.firebase_uid)
    if not perfil_profissional:
        raise HTTPException(status_code=404, detail="Perfil profissional não encontrado.")

    return crud.listar_horarios_trabalho(db, perfil_profissional['id'])

@app.post("/me/bloqueios", response_model=schemas.Bloqueio, tags=["Profissional - Autogestão"])
def criar_meu_bloqueio(
    bloqueio_data: schemas.Bloqueio,
    negocio_id: str = Depends(validate_negocio_id),
    profissional_user: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """(Profissional) Cria um bloqueio em sua agenda."""
    perfil_profissional = crud.buscar_profissional_por_uid(db, negocio_id, profissional_user.firebase_uid)
    if not perfil_profissional:
        raise HTTPException(status_code=404, detail="Perfil profissional não encontrado.")
    
    return crud.criar_bloqueio(db, perfil_profissional['id'], bloqueio_data)

@app.delete("/me/bloqueios/{bloqueio_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Profissional - Autogestão"])
def deletar_meu_bloqueio(
    bloqueio_id: str,
    negocio_id: str = Depends(validate_negocio_id),
    profissional_user: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """(Profissional) Deleta um bloqueio de sua agenda."""
    perfil_profissional = crud.buscar_profissional_por_uid(db, negocio_id, profissional_user.firebase_uid)
    if not perfil_profissional:
        raise HTTPException(status_code=404, detail="Perfil profissional não encontrado.")
        
    if not crud.deletar_bloqueio(db, perfil_profissional['id'], bloqueio_id):
        raise HTTPException(status_code=404, detail="Bloqueio não encontrado.")
    
    return

@app.get("/me/pacientes", response_model=List[schemas.PacienteProfile], tags=["Profissional - Autogestão"])
def listar_meus_pacientes(
    negocio_id: str = Depends(validate_negocio_id),
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """
    (Profissional/Enfermeiro ou Técnico)
    Lista todos os pacientes vinculados ao usuário logado, com base na sua role.
    """
    user_role = current_user.roles.get(negocio_id)
    if user_role not in ["profissional", "tecnico"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado: esta operação é apenas para profissionais (enfermeiros) ou técnicos."
        )

    pacientes = crud.listar_pacientes_por_profissional_ou_tecnico(db, negocio_id, current_user.id, user_role)
    return pacientes

# =================================================================================
# ENDPOINTS DE FEED E INTERAÇÕES
# =================================================================================

@app.post("/postagens", response_model=schemas.PostagemResponse, tags=["Feed e Interações"])
def criar_postagem(
    postagem_data: schemas.PostagemCreate,
    negocio_id: str = Depends(validate_negocio_id),
    profissional_user: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """(Profissional) Cria uma nova postagem no feed do negócio."""
    perfil_profissional = crud.buscar_profissional_por_uid(db, negocio_id, profissional_user.firebase_uid)
    if not perfil_profissional:
        raise HTTPException(status_code=404, detail="Perfil profissional não encontrado para este usuário neste negócio.")
    
    postagem_data.profissional_id = perfil_profissional['id']
    postagem_data.negocio_id = negocio_id
    
    return crud.criar_postagem(db, postagem_data, perfil_profissional)

@app.get("/feed", response_model=List[schemas.PostagemResponse], tags=["Feed e Interações"])
def get_feed(
    negocio_id: str,
    db: firestore.client = Depends(get_db),
    current_user: Optional[schemas.UsuarioProfile] = Depends(get_optional_current_user_firebase)
):
    """(Público) Retorna o feed de postagens de um negócio específico."""
    user_id = current_user.id if current_user else None
    return crud.listar_feed_por_negocio(db, negocio_id, user_id)

@app.post("/postagens/{postagem_id}/curtir", tags=["Feed e Interações"])
def curtir_postagem(
    postagem_id: str,
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """(Autenticado) Curte ou descurte uma postagem."""
    resultado = crud.toggle_curtida(db, postagem_id, current_user.id)
    return {"curtido": resultado}

@app.post("/comentarios", response_model=schemas.ComentarioResponse, tags=["Feed e Interações"])
def criar_comentario(
    comentario_data: schemas.ComentarioCreate,
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """(Autenticado) Adiciona um comentário a uma postagem."""
    return crud.criar_comentario(db, comentario_data, current_user)

@app.get("/comentarios/{postagem_id}", response_model=List[schemas.ComentarioResponse], tags=["Feed e Interações"])
def get_comentarios(
    postagem_id: str,
    db: firestore.client = Depends(get_db)
):
    """(Público) Lista todos os comentários de uma postagem."""
    return crud.listar_comentarios(db, postagem_id)

@app.delete("/postagens/{postagem_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Feed e Interações"])
def deletar_postagem(
    postagem_id: str,
    negocio_id: str = Depends(validate_negocio_id),
    profissional_user: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """(Profissional) Deleta uma de suas postagens."""
    perfil_profissional = crud.buscar_profissional_por_uid(db, negocio_id, profissional_user.firebase_uid)
    if not perfil_profissional:
        raise HTTPException(status_code=404, detail="Perfil profissional não encontrado.")
        
    if not crud.deletar_postagem(db, postagem_id, perfil_profissional['id']):
        raise HTTPException(status_code=403, detail="Postagem não encontrada ou não pertence a este profissional.")
    
    return

@app.delete("/comentarios/{comentario_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Feed e Interações"])
def deletar_comentario(
    comentario_id: str,
    postagem_id: str = Query(..., description="ID da postagem à qual o comentário pertence."),
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """(Autenticado) Deleta um de seus comentários."""
    if not crud.deletar_comentario(db, postagem_id, comentario_id, current_user.id):
        raise HTTPException(status_code=403, detail="Comentário não encontrado ou você não tem permissão para deletá-lo.")
        
    return

# =================================================================================
# ENDPOINTS DE AVALIAÇÕES
# =================================================================================

@app.post("/avaliacoes", response_model=schemas.AvaliacaoResponse, status_code=status.HTTP_201_CREATED, tags=["Avaliações"])
def criar_avaliacao(
    avaliacao_data: schemas.AvaliacaoCreate,
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """(Cliente) Cria uma nova avaliação para um profissional."""
    return crud.criar_avaliacao(db, avaliacao_data, current_user)

@app.get("/avaliacoes/{profissional_id}", response_model=List[schemas.AvaliacaoResponse], tags=["Avaliações"])
def listar_avaliacoes(
    profissional_id: str,
    db: firestore.client = Depends(get_db)
):
    """(Público) Lista todas as avaliações de um profissional."""
    return crud.listar_avaliacoes_por_profissional(db, profissional_id)

# =================================================================================
# ENDPOINTS DE NOTIFICAÇÕES
# =================================================================================

@app.get("/notificacoes", response_model=List[schemas.NotificacaoResponse], tags=["Notificações"])
def get_notificacoes(
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """(Autenticado) Retorna o histórico de notificações do usuário."""
    return crud.listar_notificacoes(db, current_user.id)

@app.get("/notificacoes/nao-lidas/contagem", response_model=schemas.NotificacaoContagemResponse, tags=["Notificações"])
def get_contagem_notificacoes_nao_lidas(
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """(Autenticado) Retorna o número de notificações não lidas."""
    count = crud.contar_notificacoes_nao_lidas(db, current_user.id)
    return {"count": count}

@app.post("/notificacoes/ler-todas", status_code=status.HTTP_204_NO_CONTENT, tags=["Notificações"])
def marcar_todas_como_lidas(
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """(Autenticado) Marca todas as notificações do usuário como lidas."""
    crud.marcar_todas_como_lidas(db, current_user.id)
    return

@app.post("/notificacoes/agendar", response_model=schemas.NotificacaoAgendadaResponse, tags=["Notificações"])
def agendar_notificacao_endpoint(
    notificacao_data: schemas.NotificacaoAgendadaCreate,
    negocio_id: str = Depends(validate_negocio_id),
    current_user: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """(Profissional/Enfermeiro) Agenda o envio de uma notificação para um paciente."""
    paciente_doc = db.collection('usuarios').document(notificacao_data.paciente_id).get()
    if not paciente_doc.exists:
        raise HTTPException(status_code=404, detail="Paciente não encontrado.")

    paciente_data = paciente_doc.to_dict()
    if paciente_data.get('enfermeiro_id') != current_user.id:
        raise HTTPException(status_code=403, detail="Acesso negado: você não está vinculado a este paciente.")
    if negocio_id not in paciente_data.get('roles', {}):
        raise HTTPException(status_code=400, detail="Paciente não pertence a este negócio.")

    notificacao_data.negocio_id = negocio_id
    agendamento = crud.agendar_notificacao(db, notificacao_data, current_user.firebase_uid)
    return agendamento

@app.post("/notificacoes/marcar-como-lida", status_code=status.HTTP_204_NO_CONTENT, tags=["Notificações"])
def marcar_como_lida(
    request: schemas.MarcarLidaRequest,
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """(Autenticado) Marca uma notificação específica como lida."""
    crud.marcar_notificacao_como_lida(db, current_user.id, request.notificacao_id)
    return

# =================================================================================
# ENDPOINTS DE USUÁRIOS E AUTENTICAÇÃO
# =================================================================================

@app.post("/users/sync-profile", response_model=schemas.UsuarioProfile, tags=["Usuários"])
def sync_user_profile(
    user_data: schemas.UsuarioSync,
    db: firestore.client = Depends(get_db)
):
    """
    Sincroniza os dados do usuário do Firebase Auth com o Firestore.
    Cria um perfil de usuário no banco de dados na primeira vez que ele faz login.
    """
    try:
        user_profile_data = crud.criar_ou_atualizar_usuario(db, user_data)
        
        # Garante que a resposta da API sempre corresponda ao schema de dados.
        # Isso corrige problemas de campos ausentes ou com valores null.
        user_profile_response = schemas.UsuarioProfile(**user_profile_data)
        
        # Adiciona o profissional_id ao perfil antes de retornar, se o perfil existir.
        if user_profile_response.roles:
            for negocio_id, role in user_profile_response.roles.items():
                if role in ['admin', 'profissional']:
                    perfil_profissional = crud.buscar_profissional_por_uid(db, negocio_id, user_profile_response.firebase_uid)
                    if perfil_profissional:
                        user_profile_response.profissional_id = perfil_profissional.get('id')
                        break
        
        return user_profile_response

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Erro inesperado ao sincronizar perfil do usuário: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ocorreu um erro interno no servidor.")

@app.get("/me/profile", response_model=schemas.UsuarioProfile, tags=["Usuários"])
def get_me_profile(current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase)):
    """Retorna o perfil completo do usuário autenticado."""
    return current_user

@app.post("/me/register-fcm-token", status_code=status.HTTP_200_OK, tags=["Usuários"])
def register_fcm_token_endpoint(
    request: schemas.FCMTokenUpdate,
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """Registra ou atualiza o token de notificação (FCM) para o dispositivo do usuário."""
    crud.adicionar_fcm_token(db, current_user.firebase_uid, request.fcm_token)
    return {"message": "FCM token registrado com sucesso."}

@app.get("/negocios/{negocio_id}/admin-status", tags=["Admin - Gestão do Negócio"])
def get_admin_status(
    negocio_id: str,
    db: firestore.client = Depends(get_db)
):
    """
    (Público) Verifica se um negócio já possui um administrador.
    """
    has_admin = crud.check_admin_status(db, negocio_id)
    return {"has_admin": has_admin}

# =================================================================================
# ENDPOINTS DE PROFISSIONAIS (Públicos)
# =================================================================================

@app.get("/profissionais", response_model=List[schemas.ProfissionalResponse], tags=["Profissionais"])
def listar_profissionais(
    negocio_id: str,
    db: firestore.client = Depends(get_db)
):
    """Lista todos os profissionais ativos de um negócio específico."""
    return crud.listar_profissionais_por_negocio(db, negocio_id)

@app.get("/profissionais/{profissional_id}", response_model=schemas.ProfissionalResponse, tags=["Profissionais"])
def get_profissional_details(
    profissional_id: str,
    db: firestore.client = Depends(get_db)
):
    """Retorna os detalhes de um profissional específico, incluindo seus serviços."""
    profissional = crud.buscar_profissional_por_id(db, profissional_id)
    if not profissional:
        raise HTTPException(status_code=404, detail="Profissional não encontrado.")
    
    servicos = crud.listar_servicos_por_profissional(db, profissional_id)
    profissional['servicos'] = servicos
    
    postagens = crud.listar_postagens_por_profissional(db, profissional_id)
    profissional['postagens'] = postagens
    
    avaliacoes = crud.listar_avaliacoes_por_profissional(db, profissional_id)
    profissional['avaliacoes'] = avaliacoes
    
    return profissional

# =================================================================================
# ENDPOINTS DE AGENDAMENTOS E DISPONIBILIDADE PÚBLICA
# =================================================================================

@app.get("/profissionais/{profissional_id}/horarios-disponiveis", tags=["Agendamentos"])
def get_horarios_disponiveis(
    profissional_id: str,
    dia: date = Query(..., description="Dia para verificar a disponibilidade (formato: AAAA-MM-DD)."),
    duracao_servico: int = Query(60, description="Duração do serviço em minutos para calcular os slots."),
    db: firestore.client = Depends(get_db)
):
    """(Público) Calcula e retorna os horários livres de um profissional em um dia específico."""
    return crud.calcular_horarios_disponiveis(db, profissional_id, dia, duracao_servico)

@app.post("/agendamentos", response_model=schemas.AgendamentoResponse, tags=["Agendamentos"])
def agendar(
    agendamento: schemas.AgendamentoCreate,
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """(Cliente) Cria um novo agendamento para o usuário autenticado."""
    try:
        novo_agendamento = crud.criar_agendamento(db, agendamento, current_user)
        return novo_agendamento
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Erro inesperado ao criar agendamento: {e}")
        raise HTTPException(status_code=500, detail="Ocorreu um erro ao criar o agendamento.")

@app.get("/agendamentos/me", response_model=List[schemas.AgendamentoResponse], tags=["Agendamentos"])
def listar_meus_agendamentos_cliente(
    negocio_id: str = Header(..., description="ID do Negócio para filtrar os agendamentos."),
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """(Cliente) Lista todos os agendamentos do cliente autenticado em um negócio específico."""
    return crud.listar_agendamentos_por_cliente(db, negocio_id, current_user.id)

@app.delete("/agendamentos/{agendamento_id}", status_code=status.HTTP_200_OK, tags=["Agendamentos"])
def cancelar_agendamento_endpoint(
    agendamento_id: str,
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """(Cliente) Permite ao cliente autenticado cancelar um de seus agendamentos."""
    agendamento_cancelado = crud.cancelar_agendamento(db, agendamento_id, current_user.id)
    
    if agendamento_cancelado is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agendamento não encontrado ou você não tem permissão para cancelá-lo."
        )
    
    return {"message": "Agendamento cancelado com sucesso."}

@app.get("/me/agendamentos", response_model=List[schemas.AgendamentoResponse], tags=["Profissional - Autogestão"])
def listar_meus_agendamentos_profissional(
    negocio_id: str = Header(..., description="ID do Negócio no qual o profissional está atuando."),
    profissional_user: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """(Profissional) Lista todos os agendamentos recebidos."""
    perfil_profissional = crud.buscar_profissional_por_uid(db, negocio_id, profissional_user.firebase_uid)
    if not perfil_profissional:
        raise HTTPException(status_code=404, detail="Perfil profissional não encontrado.")
    
    return crud.listar_agendamentos_por_profissional(db, negocio_id, perfil_profissional['id'])

@app.patch("/me/agendamentos/{agendamento_id}/cancelar", response_model=schemas.AgendamentoResponse, tags=["Profissional - Autogestão"])
def cancelar_agendamento_pelo_profissional_endpoint(
    agendamento_id: str,
    negocio_id: str = Header(..., description="ID do Negócio no qual o profissional está atuando."),
    profissional_user: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """(Profissional) Cancela um agendamento que recebeu."""
    perfil_profissional = crud.buscar_profissional_por_uid(db, negocio_id, profissional_user.firebase_uid)
    if not perfil_profissional:
        raise HTTPException(status_code=404, detail="Perfil profissional não encontrado.")
    
    agendamento_cancelado = crud.cancelar_agendamento_pelo_profissional(db, agendamento_id, perfil_profissional['id'])
    if not agendamento_cancelado:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado ou não pertence a este profissional.")
        
    return agendamento_cancelado

# =================================================================================
# ENDPOINT DE UPLOAD DE FOTOS
# =================================================================================

async def upload_and_resize_image(
    file_content: bytes,
    filename_base: str,
    bucket_name: str,
    content_type: str
) -> dict:
    """Função auxiliar para upload e redimensionamento de imagens no Cloud Storage."""
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    urls = {}
    extension = ".jpeg"
    
    image = Image.open(BytesIO(file_content))
    if image.mode in ('RGBA', 'P'):
        image = image.convert('RGB')

    buffer_original = BytesIO()
    image.save(buffer_original, format="JPEG", quality=90)
    buffer_original.seek(0)
    original_blob_name = f"uploads/{filename_base}_original{extension}"
    original_blob = bucket.blob(original_blob_name)
    original_blob.upload_from_string(buffer_original.getvalue(), content_type="image/jpeg")
    urls['original'] = original_blob.public_url

    image.thumbnail((800, 800))
    buffer_medium = BytesIO()
    image.save(buffer_medium, format="JPEG", quality=85)
    buffer_medium.seek(0)
    medium_blob_name = f"uploads/{filename_base}_medium{extension}"
    medium_blob = bucket.blob(medium_blob_name)
    medium_blob.upload_from_string(buffer_medium.getvalue(), content_type="image/jpeg")
    urls['medium'] = medium_blob.public_url

    image.thumbnail((200, 200))
    buffer_thumbnail = BytesIO()
    image.save(buffer_thumbnail, format="JPEG", quality=80)
    buffer_thumbnail.seek(0)
    thumbnail_blob_name = f"uploads/{filename_base}_thumbnail{extension}"
    thumbnail_blob = bucket.blob(thumbnail_blob_name)
    thumbnail_blob.upload_from_string(buffer_thumbnail.getvalue(), content_type="image/jpeg")
    urls['thumbnail'] = thumbnail_blob.public_url

    return urls

@app.post("/upload-foto", tags=["Utilitários"])
async def upload_foto(
    file: UploadFile = File(...),
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase)
):
    """(Autenticado) Faz o upload de uma foto, redimensiona e retorna as URLs."""
    if not CLOUD_STORAGE_BUCKET_NAME_GLOBAL:
        raise HTTPException(status_code=500, detail="Bucket do Cloud Storage não configurado.")
    
    try:
        file_content = await file.read()
        filename_base = f"{uuid.uuid4()}-{os.path.splitext(file.filename)[0]}"
        
        uploaded_urls = await upload_and_resize_image(
            file_content=file_content,
            filename_base=filename_base,
            bucket_name=CLOUD_STORAGE_BUCKET_NAME_GLOBAL,
            content_type=file.content_type
        )
        return JSONResponse(content=uploaded_urls)
    except Exception as e:
        logger.error(f"ERRO CRÍTICO NO UPLOAD: {e}")
        raise HTTPException(status_code=500, detail=f"Ocorreu um erro interno no servidor: {e}")

# =================================================================================
# FUNÇÃO AUXILIAR PARA UPLOAD DE ARQUIVOS GENÉRICOS
# =================================================================================

async def upload_generic_file(
    file_content: bytes,
    filename: str,
    bucket_name: str,
    content_type: str
) -> str:
    """Função auxiliar para upload de arquivos genéricos no Cloud Storage."""
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    
    unique_filename = f"uploads/anexos/{uuid.uuid4()}-{filename}"
    
    blob = bucket.blob(unique_filename)
    blob.upload_from_string(file_content, content_type=content_type)
    
    return blob.public_url

# =================================================================================
# ENDPOINT DE UPLOAD GENÉRICO
# =================================================================================

@app.post("/upload-file", tags=["Utilitários"])
async def upload_file_endpoint(
    file: UploadFile = File(...),
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase)
):
    """(Autenticado) Faz o upload de um arquivo genérico (PDF, DOCX, etc.) e retorna a URL."""
    if not CLOUD_STORAGE_BUCKET_NAME_GLOBAL:
        raise HTTPException(status_code=500, detail="Bucket do Cloud Storage não configurado.")
    
    try:
        file_content = await file.read()
        
        uploaded_url = await upload_generic_file(
            file_content=file_content,
            filename=file.filename,
            bucket_name=CLOUD_STORAGE_BUCKET_NAME_GLOBAL,
            content_type=file.content_type
        )
        return JSONResponse(content={"url": uploaded_url})
    except Exception as e:
        logger.error(f"ERRO CRÍTICO NO UPLOAD DE ARQUIVO: {e}")
        raise HTTPException(status_code=500, detail=f"Ocorreu um erro interno no servidor: {e}")

# =================================================================================
# ENDPOINTS DA PESQUISA DE SATISFAÇÃO
# =================================================================================

@app.post("/negocios/{negocio_id}/pesquisas/enviar", response_model=schemas.PesquisaEnviadaResponse, tags=["Pesquisa de Satisfação"])
def enviar_pesquisa(
    negocio_id: str,
    envio_data: schemas.PesquisaEnviadaCreate,
    admin: schemas.UsuarioProfile = Depends(get_current_admin_user),
    db: firestore.client = Depends(get_db)
):
    """(Admin) Envia uma pesquisa de satisfação para um paciente."""
    envio_data.negocio_id = negocio_id
    return crud.enviar_pesquisa_satisfacao(db, envio_data)

@app.get("/me/pesquisas", response_model=List[schemas.PesquisaEnviadaResponse], tags=["Pesquisa de Satisfação"])
def listar_minhas_pesquisas(
    negocio_id: str = Header(..., description="ID do Negócio para filtrar as pesquisas."),
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """(Paciente) Lista todas as pesquisas de satisfação recebidas."""
    return crud.listar_pesquisas_por_paciente(db, negocio_id, current_user.id)

@app.post("/me/pesquisas/{pesquisa_id}/submeter", response_model=schemas.PesquisaEnviadaResponse, tags=["Pesquisa de Satisfação"])
def submeter_respostas(
    pesquisa_id: str,
    respostas_data: schemas.SubmeterPesquisaRequest,
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """(Paciente) Submete as respostas para uma pesquisa de satisfação."""
    pesquisa_atualizada = crud.submeter_respostas_pesquisa(db, pesquisa_id, respostas_data, current_user.id)
    if not pesquisa_atualizada:
        raise HTTPException(status_code=404, detail="Pesquisa não encontrada ou não pertence a este paciente.")
    return pesquisa_atualizada

@app.get("/negocios/{negocio_id}/pesquisas/resultados", response_model=List[schemas.PesquisaEnviadaResponse], tags=["Pesquisa de Satisfação"])
def get_resultados_pesquisas(
    negocio_id: str,
    modelo_pesquisa_id: Optional[str] = Query(None, description="Filtre os resultados por um modelo de pesquisa específico."),
    admin: schemas.UsuarioProfile = Depends(get_current_admin_user),
    db: firestore.client = Depends(get_db)
):
    """(Admin) Lista todos os resultados das pesquisas de satisfação respondidas."""
    return crud.listar_resultados_pesquisas(db, negocio_id, modelo_pesquisa_id)

# =================================================================================
# ENDPOINTS DO FLUXO DO TÉCNICO (BASEADO NO PDF ESTRATÉGIA)
# =================================================================================

@app.post("/pacientes/{paciente_id}/confirmar-leitura-plano", response_model=schemas.ConfirmacaoLeituraResponse, tags=["Fluxo do Técnico"])
def confirmar_leitura_plano(
    paciente_id: str,
    confirmacao: schemas.ConfirmacaoLeituraCreate,
    current_user: schemas.UsuarioProfile = Depends(get_current_tecnico_user),
    db: firestore.client = Depends(get_db)
):
    """(Técnico) Confirma a leitura do plano de cuidado, criando a trilha de auditoria."""
    if confirmacao.usuario_id != current_user.id:
        raise HTTPException(status_code=403, detail="Acesso negado: o usuario_id deve ser o do técnico autenticado.")
    return crud.registrar_confirmacao_leitura_plano(db, paciente_id, confirmacao)

@app.get("/pacientes/{paciente_id}/verificar-leitura-plano", tags=["Fluxo do Técnico"])
def verificar_leitura_plano(
    paciente_id: str,
    data: date = Query(..., description="Data para verificar a leitura (formato: YYYY-MM-DD)."),
    current_user: schemas.UsuarioProfile = Depends(get_current_tecnico_user),
    db: firestore.client = Depends(get_db)
):
    """(Técnico) Verifica se a leitura foi confirmada para liberar as outras funções do dia."""
    leitura_confirmada = crud.verificar_leitura_plano_do_dia(db, paciente_id, current_user.id, data)
    return {"leitura_confirmada": leitura_confirmada}

@app.post("/pacientes/{paciente_id}/confirmar-leitura", response_model=schemas.ConfirmacaoLeituraResponse, tags=["Fluxo do Técnico"])
def confirmar_leitura_alias(
    paciente_id: str,
    confirmacao: schemas.ConfirmacaoLeituraCreate,
    current_user: schemas.UsuarioProfile = Depends(get_current_tecnico_user),
    db: firestore.client = Depends(get_db)
):
    """Alias: confirma a leitura do plano (mesma lógica de /confirmar-leitura-plano)."""
    if confirmacao.usuario_id != current_user.id:
        raise HTTPException(status_code=403, detail="Acesso negado: o usuario_id deve ser o do técnico autenticado.")
    return crud.registrar_confirmacao_leitura_plano(db, paciente_id, confirmacao)

@app.get("/pacientes/{paciente_id}/confirmar-leitura/status", tags=["Fluxo do Técnico"])
def confirmar_leitura_status_alias(
    paciente_id: str,
    # A data agora é opcional e, se não for fornecida, usa a data atual.
    data: date = Query(default_factory=date.today, description="Data para verificar a leitura (padrão: hoje)."),
    current_user: schemas.UsuarioProfile = Depends(get_current_tecnico_user),
    db: firestore.client = Depends(get_db)
):
    """Alias: verifica o status de leitura (equivalente a /verificar-leitura-plano)."""
    # Esta linha agora retorna o objeto JSON completo que o app precisa.
    status_leitura = crud.verificar_leitura_plano_do_dia(db, paciente_id, current_user.id, data)
    return status_leitura

@app.get("/pacientes/{paciente_id}/checklist-diario", response_model=List[schemas.ChecklistItemDiarioResponse], tags=["Fluxo do Técnico"])
def get_checklist_diario(
    paciente_id: str,
    data: date = Query(..., description="Data do checklist (formato: YYYY-MM-DD)."),
    negocio_id: str = Header(..., alias="negocio-id", description="ID do Negócio."),
    current_user: schemas.UsuarioProfile = Depends(get_paciente_autorizado),
    db: firestore.client = Depends(get_db),
):
    """
    (Técnico, Profissional ou Admin) Retorna o checklist do dia, baseado EXCLUSIVAMENTE no plano de cuidado mais recente.
    Se o plano mais recente não tiver checklist, retorna uma lista vazia.
    Se não existir, o checklist do dia é replicado a partir do plano ativo.
    """
    # ALTERAÇÃO AQUI: Chame a nova função corrigida
    return crud.get_checklist_diario_plano_ativo(db, paciente_id, data, negocio_id)


@app.patch("/pacientes/{paciente_id}/checklist-diario/{item_id}", response_model=schemas.ChecklistItemDiarioResponse, tags=["Fluxo do Técnico"])
def update_checklist_item_diario(
    paciente_id: str,
    item_id: str,
    data: date = Query(..., description="Data do checklist (formato: YYYY-MM-DD)."),
    update_data: schemas.ChecklistItemDiarioUpdate = ...,
    current_user: schemas.UsuarioProfile = Depends(get_current_tecnico_user),
    db: firestore.client = Depends(get_db)
):
    """(Técnico) Permite marcar/desmarcar um item do checklist."""
    if not crud.verificar_leitura_plano_do_dia(db, paciente_id, current_user.id, data):
        raise HTTPException(status_code=403, detail="Leitura do Plano Ativo pendente para hoje.")
    item_atualizado = crud.atualizar_item_checklist_diario(db, paciente_id, item_id, update_data)
    if not item_atualizado:
        raise HTTPException(status_code=404, detail="Item do checklist não encontrado.")
    return item_atualizado


# =================================================================================
# 1. NOVOS ENDPOINTS: ANAMNESE
# =================================================================================

@app.post("/pacientes/{paciente_id}/anamnese", response_model=schemas.AnamneseEnfermagemResponse, status_code=status.HTTP_201_CREATED, tags=["Anamnese"])
def criar_anamnese(
    paciente_id: str,
    anamnese_data: schemas.AnamneseEnfermagemCreate,
    current_user: schemas.UsuarioProfile = Depends(get_current_admin_or_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """(Admin ou Enfermeiro) Cria uma nova ficha de anamnese para um paciente."""
    return crud.criar_anamnese(db, paciente_id, anamnese_data)

@app.get("/pacientes/{paciente_id}/anamnese", response_model=List[schemas.AnamneseEnfermagemResponse], tags=["Anamnese"])
def listar_anamneses(
    paciente_id: str,
    current_user: schemas.UsuarioProfile = Depends(get_paciente_autorizado),
    db: firestore.client = Depends(get_db)
):
    """(Autorizado) Lista todas as fichas de anamnese de um paciente."""
    return crud.listar_anamneses_por_paciente(db, paciente_id)

@app.put("/anamnese/{anamnese_id}", response_model=schemas.AnamneseEnfermagemResponse, tags=["Anamnese"])
def atualizar_anamnese(
    anamnese_id: str,
    paciente_id: str = Query(..., description="ID do paciente a quem a anamnese pertence."),
    update_data: schemas.AnamneseEnfermagemUpdate = ...,
    current_user: schemas.UsuarioProfile = Depends(get_current_admin_or_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """(Admin ou Enfermeiro) Atualiza uma ficha de anamnese existente."""
    anamnese_atualizada = crud.atualizar_anamnese(db, anamnese_id, paciente_id, update_data)
    if not anamnese_atualizada:
        raise HTTPException(status_code=404, detail="Ficha de anamnese não encontrada.")
    return anamnese_atualizada

# =================================================================================
# 2. NOVO ENDPOINT: ENDEREÇO
# =================================================================================

@app.put("/pacientes/{paciente_id}/endereco", response_model=schemas.UsuarioProfile, tags=["Pacientes"])
def atualizar_endereco_paciente(
    paciente_id: str,
    endereco_data: schemas.EnderecoUpdate,
    current_user: schemas.UsuarioProfile = Depends(get_current_admin_or_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """(Admin ou Enfermeiro) Adiciona ou atualiza o endereço de um paciente."""
    paciente_atualizado = crud.atualizar_endereco_paciente(db, paciente_id, endereco_data)
    if not paciente_atualizado:
        raise HTTPException(status_code=404, detail="Paciente não encontrado.")
    return paciente_atualizado
    