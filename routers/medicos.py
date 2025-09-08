# routers/medicos.py
"""
Router para relatórios médicos e fluxos médicos
"""

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from typing import List, Optional
import schemas
import crud
from database import get_db
from auth import (
    get_current_user_firebase, get_current_medico_user,
    get_relatorio_autorizado, validate_negocio_id
)
from firebase_admin import firestore
import uuid
import os

router = APIRouter(tags=["Relatórios Médicos", "Relatórios Médicos - Médico"])

# =================================================================================
# ENDPOINTS DE RELATÓRIOS MÉDICOS - CRIAÇÃO E LISTAGEM
# =================================================================================

@router.post("/pacientes/{paciente_id}/relatorios", response_model=schemas.RelatorioMedicoResponse, status_code=status.HTTP_201_CREATED)
def criar_relatorio_medico(
    paciente_id: str,
    relatorio_data: schemas.RelatorioMedicoCreate,
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """Cria uma solicitação de relatório médico para um paciente."""
    # Verificar se o usuário tem permissão para solicitar relatórios
    if not any(role in ['admin', 'profissional', 'enfermeiro', 'tecnico'] 
               for role in (current_user.roles or {}).values()):
        raise HTTPException(
            status_code=403,
            detail="Apenas profissionais de saúde podem solicitar relatórios médicos"
        )
    
    return crud.criar_relatorio_medico(db, paciente_id, relatorio_data, current_user)

@router.get("/pacientes/{paciente_id}/relatorios", response_model=List[schemas.RelatorioMedicoResponse])
def listar_relatorios_paciente(
    paciente_id: str,
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """Lista todos os relatórios médicos de um paciente."""
    # Verificar se o usuário tem acesso ao paciente
    user_roles = current_user.roles or {}
    
    # Admins e profissionais podem ver relatórios de pacientes do seu negócio
    has_access = False
    for negocio_id, role in user_roles.items():
        if role in ['admin', 'profissional', 'medico', 'enfermeiro', 'tecnico']:
            has_access = True
            break
    
    if not has_access:
        raise HTTPException(
            status_code=403,
            detail="Você não tem permissão para acessar os relatórios deste paciente"
        )
    
    return crud.listar_relatorios_por_paciente(db, paciente_id)

@router.post("/relatorios/{relatorio_id}/fotos", response_model=schemas.RelatorioMedicoResponse)
async def adicionar_fotos_relatorio(
    relatorio_id: str,
    files: List[UploadFile] = File(...),
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """Adiciona fotos a um relatório médico existente."""
    # Verificar se o relatório existe e o usuário tem acesso
    relatorio_doc = db.collection('relatorios_medicos').document(relatorio_id).get()
    if not relatorio_doc.exists:
        raise HTTPException(status_code=404, detail="Relatório não encontrado")
    
    relatorio_data = relatorio_doc.to_dict()
    
    # Verificar permissões
    user_roles = current_user.roles or {}
    negocio_id = relatorio_data.get('negocio_id')
    user_role = user_roles.get(negocio_id) if negocio_id else None
    
    if user_role not in ['admin', 'profissional', 'medico', 'enfermeiro', 'tecnico']:
        raise HTTPException(
            status_code=403,
            detail="Você não tem permissão para adicionar fotos a este relatório"
        )
    
    # Processar arquivos de fotos
    fotos_urls = []
    
    for file in files:
        # Verificar tipo de arquivo
        allowed_types = ["image/jpeg", "image/png", "image/jpg"]
        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail=f"Tipo de arquivo '{file.content_type}' não suportado. Use apenas JPEG, PNG ou JPG."
            )
        
        # Verificar tamanho do arquivo (max 10MB por foto)
        if file.size and file.size > 10 * 1024 * 1024:
            raise HTTPException(
                status_code=400,
                detail=f"Arquivo '{file.filename}' muito grande. Máximo 10MB por foto."
            )
        
        # Gerar nome único para o arquivo
        file_extension = file.filename.split('.')[-1] if file.filename else 'jpg'
        unique_filename = f"relatorio_{relatorio_id}_{uuid.uuid4()}.{file_extension}"
        
        # Criar diretório se não existir
        upload_dir = os.path.join("uploads", "relatorios")
        os.makedirs(upload_dir, exist_ok=True)
        
        # Salvar arquivo
        file_path = os.path.join(upload_dir, unique_filename)
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # URL para acesso ao arquivo
        foto_url = f"/uploads/relatorios/{unique_filename}"
        fotos_urls.append(foto_url)
    
    # Atualizar relatório com as URLs das fotos
    fotos_existentes = relatorio_data.get('fotos', [])
    todas_fotos = fotos_existentes + fotos_urls
    
    db.collection('relatorios_medicos').document(relatorio_id).update({
        'fotos': todas_fotos,
        'updated_at': firestore.SERVER_TIMESTAMP
    })
    
    # Retornar relatório atualizado
    relatorio_atualizado = db.collection('relatorios_medicos').document(relatorio_id).get()
    result = relatorio_atualizado.to_dict()
    result['id'] = relatorio_atualizado.id
    
    return result

# =================================================================================
# ENDPOINTS ESPECÍFICOS PARA MÉDICOS
# =================================================================================

@router.get("/medico/relatorios/pendentes", response_model=List[schemas.RelatorioMedicoResponse])
def listar_relatorios_pendentes_medico(
    negocio_id: str = Depends(validate_negocio_id),
    current_user: schemas.UsuarioProfile = Depends(get_current_medico_user),
    db: firestore.client = Depends(get_db)
):
    """Lista todos os relatórios pendentes para o médico autenticado."""
    return crud.listar_relatorios_pendentes_medico(db, current_user.id, negocio_id)

@router.get("/medico/relatorios", response_model=List[schemas.RelatorioMedicoResponse])
def listar_historico_relatorios_medico(
    status_filter: Optional[str] = None,
    negocio_id: str = Depends(validate_negocio_id),
    current_user: schemas.UsuarioProfile = Depends(get_current_medico_user),
    db: firestore.client = Depends(get_db)
):
    """Lista o histórico de relatórios do médico autenticado."""
    return crud.listar_historico_relatorios_medico(db, current_user.id, negocio_id, status_filter)

@router.get("/relatorios/{relatorio_id}", response_model=schemas.RelatorioCompletoResponse)
def obter_relatorio_completo(
    relatorio_id: str,
    current_user: schemas.UsuarioProfile = Depends(get_relatorio_autorizado),
    db: firestore.client = Depends(get_db)
):
    """Obtém os detalhes completos de um relatório médico."""
    # Buscar relatório
    relatorio_doc = db.collection('relatorios_medicos').document(relatorio_id).get()
    if not relatorio_doc.exists:
        raise HTTPException(status_code=404, detail="Relatório não encontrado")
    
    relatorio_data = relatorio_doc.to_dict()
    relatorio_data['id'] = relatorio_doc.id
    
    # Buscar dados do paciente
    paciente_id = relatorio_data.get('paciente_id')
    if paciente_id:
        paciente_doc = db.collection('usuarios').document(paciente_id).get()
        if paciente_doc.exists:
            paciente_data = paciente_doc.to_dict()
            # Descriptografar dados sensíveis do paciente
            paciente_data = crud.decrypt_user_sensitive_fields(paciente_data, ['nome', 'telefone'])
            relatorio_data['paciente'] = {
                'id': paciente_doc.id,
                'nome': paciente_data.get('nome'),
                'email': paciente_data.get('email'),
                'data_nascimento': paciente_data.get('data_nascimento')
            }
    
    return relatorio_data

@router.post("/relatorios/{relatorio_id}/aprovar", response_model=schemas.RelatorioMedicoResponse)
def aprovar_relatorio_medico(
    relatorio_id: str,
    aprovacao_data: schemas.RelatorioAprovacao,
    current_user: schemas.UsuarioProfile = Depends(get_current_medico_user),
    db: firestore.client = Depends(get_db)
):
    """Aprova um relatório médico pendente."""
    # Atualizar relatório
    update_data = schemas.RelatorioMedicoUpdate(
        status='finalizado',
        relatorio_final=aprovacao_data.relatorio_final,
        observacoes_medico=aprovacao_data.observacoes_medico
    )
    
    result = crud.atualizar_relatorio_medico(db, relatorio_id, update_data, current_user.id)
    if not result:
        raise HTTPException(status_code=404, detail="Relatório não encontrado")
    
    return result

@router.post("/relatorios/{relatorio_id}/recusar", response_model=schemas.RelatorioMedicoResponse)
def recusar_relatorio_medico(
    relatorio_id: str,
    recusa_data: schemas.RelatorioRecusa,
    current_user: schemas.UsuarioProfile = Depends(get_current_medico_user),
    db: firestore.client = Depends(get_db)
):
    """Recusa um relatório médico pendente."""
    # Atualizar relatório
    update_data = schemas.RelatorioMedicoUpdate(
        status='em_revisao',
        observacoes_medico=recusa_data.motivo_recusa
    )
    
    result = crud.atualizar_relatorio_medico(db, relatorio_id, update_data, current_user.id)
    if not result:
        raise HTTPException(status_code=404, detail="Relatório não encontrado")
    
    return result

@router.put("/relatorios/{relatorio_id}", response_model=schemas.RelatorioMedicoResponse)
def atualizar_relatorio_medico_endpoint(
    relatorio_id: str,
    update_data: schemas.RelatorioMedicoUpdate,
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """Atualiza um relatório médico."""
    # Verificar permissões
    relatorio_doc = db.collection('relatorios_medicos').document(relatorio_id).get()
    if not relatorio_doc.exists:
        raise HTTPException(status_code=404, detail="Relatório não encontrado")
    
    relatorio_data = relatorio_doc.to_dict()
    
    # Verificar se o usuário tem permissão
    user_roles = current_user.roles or {}
    negocio_id = relatorio_data.get('negocio_id')
    user_role = user_roles.get(negocio_id) if negocio_id else None
    
    if user_role not in ['admin', 'medico'] and relatorio_data.get('autor_id') != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Você não tem permissão para editar este relatório"
        )
    
    result = crud.atualizar_relatorio_medico(db, relatorio_id, update_data, current_user.id)
    if not result:
        raise HTTPException(status_code=404, detail="Não foi possível atualizar o relatório")
    
    return result