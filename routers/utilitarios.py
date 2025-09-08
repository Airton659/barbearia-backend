# routers/utilitarios.py
"""
Router para uploads, arquivos, pesquisas e utilitários diversos
"""

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query
from typing import List, Optional
import schemas
import crud
from database import get_db
from auth import (
    get_current_user_firebase, get_current_admin_user,
    get_current_tecnico_user, validate_negocio_id,
    validate_path_negocio_id
)
from firebase_admin import firestore
import uuid
import os
import logging
from PIL import Image
import base64
from io import BytesIO

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Utilitários", "Arquivos", "Pesquisa de Satisfação"])

# =================================================================================
# ENDPOINTS DE UPLOAD E ARQUIVOS
# =================================================================================

@router.post("/upload-foto")
async def upload_foto(
    foto: UploadFile = File(...),
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """Upload de foto via arquivo."""
    try:
        # Verificar tipo de arquivo
        allowed_types = ["image/jpeg", "image/png", "image/jpg"]
        if foto.content_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail="Tipo de arquivo não suportado. Use apenas JPEG, PNG ou JPG."
            )
        
        # Verificar tamanho do arquivo (max 10MB)
        if foto.size and foto.size > 10 * 1024 * 1024:
            raise HTTPException(
                status_code=400,
                detail="Arquivo muito grande. Máximo 10MB."
            )
        
        # Ler conteúdo do arquivo
        foto_bytes = await foto.read()
        
        # Processar com PIL para otimizar
        img = Image.open(BytesIO(foto_bytes))
        
        # Redimensionar se muito grande (manter proporção)
        max_size = (1920, 1080)
        if img.size[0] > max_size[0] or img.size[1] > max_size[1]:
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # Converter para RGB se necessário
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        
        # Salvar imagem otimizada
        output = BytesIO()
        img.save(output, format='JPEG', quality=85, optimize=True)
        output.seek(0)
        
        # Gerar nome único
        file_extension = 'jpg'
        unique_filename = f"{current_user.id}_{uuid.uuid4()}.{file_extension}"
        
        # Criar diretório se não existir
        upload_dir = os.path.join("uploads", "fotos")
        os.makedirs(upload_dir, exist_ok=True)
        
        # Salvar arquivo otimizado
        file_path = os.path.join(upload_dir, unique_filename)
        with open(file_path, "wb") as buffer:
            buffer.write(output.getvalue())
        
        # URL para acesso
        foto_url = f"/uploads/fotos/{unique_filename}"
        
        return {
            "message": "Foto enviada com sucesso",
            "url": foto_url,
            "filename": unique_filename,
            "size": os.path.getsize(file_path)
        }
        
    except Exception as e:
        logger.error(f"Erro no upload de foto: {e}")
        raise HTTPException(status_code=500, detail=f"Erro no upload: {str(e)}")

@router.post("/upload-file")
async def upload_file(
    file: UploadFile = File(...),
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """Upload de arquivo genérico."""
    try:
        # Verificar tamanho do arquivo (max 50MB)
        if file.size and file.size > 50 * 1024 * 1024:
            raise HTTPException(
                status_code=400,
                detail="Arquivo muito grande. Máximo 50MB."
            )
        
        # Tipos permitidos
        allowed_types = [
            "image/jpeg", "image/png", "image/jpg", "image/gif",
            "application/pdf", "text/plain", "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ]
        
        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail="Tipo de arquivo não suportado."
            )
        
        # Gerar nome único
        file_extension = file.filename.split('.')[-1] if file.filename else 'bin'
        unique_filename = f"{current_user.id}_{uuid.uuid4()}.{file_extension}"
        
        # Criar diretório se não existir
        upload_dir = os.path.join("uploads", "arquivos")
        os.makedirs(upload_dir, exist_ok=True)
        
        # Salvar arquivo
        file_path = os.path.join(upload_dir, unique_filename)
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # URL para acesso
        file_url = f"/uploads/arquivos/{unique_filename}"
        
        return {
            "message": "Arquivo enviado com sucesso",
            "url": file_url,
            "filename": unique_filename,
            "original_name": file.filename,
            "content_type": file.content_type,
            "size": os.path.getsize(file_path)
        }
        
    except Exception as e:
        logger.error(f"Erro no upload de arquivo: {e}")
        raise HTTPException(status_code=500, detail=f"Erro no upload: {str(e)}")

# =================================================================================
# ENDPOINTS DE PESQUISA DE SATISFAÇÃO
# =================================================================================

@router.post("/negocios/{negocio_id}/pesquisas/enviar", response_model=schemas.PesquisaEnviadaResponse)
def enviar_pesquisa_satisfacao(
    pesquisa_data: schemas.PesquisaEnviadaCreate,
    negocio_id: str = Depends(validate_path_negocio_id),
    admin: schemas.UsuarioProfile = Depends(get_current_admin_user),
    db: firestore.client = Depends(get_db)
):
    """Envia uma pesquisa de satisfação para clientes."""
    # Implementar lógica de envio de pesquisa
    pesquisa_dict = {
        'titulo': pesquisa_data.titulo,
        'descricao': pesquisa_data.descricao,
        'perguntas': [p.model_dump() for p in pesquisa_data.perguntas],
        'negocio_id': negocio_id,
        'enviado_por': admin.id,
        'data_envio': firestore.SERVER_TIMESTAMP,
        'ativa': True,
        'respostas_coletadas': 0
    }
    
    doc_ref = db.collection('pesquisas').document()
    doc_ref.set(pesquisa_dict)
    pesquisa_dict['id'] = doc_ref.id
    
    return pesquisa_dict

@router.get("/me/pesquisas", response_model=List[schemas.PesquisaEnviadaResponse])
def listar_minhas_pesquisas(
    negocio_id: str = Depends(validate_negocio_id),
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """Lista as pesquisas disponíveis para o usuário responder."""
    return crud.listar_pesquisas_por_paciente(db, negocio_id, current_user.id)

@router.post("/me/pesquisas/{pesquisa_id}/submeter", response_model=schemas.PesquisaEnviadaResponse)
def submeter_resposta_pesquisa(
    pesquisa_id: str,
    resposta_data: schemas.PesquisaRespostaSubmit,
    negocio_id: str = Depends(validate_negocio_id),
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """Submete as respostas de uma pesquisa."""
    # Verificar se a pesquisa existe
    pesquisa_doc = db.collection('pesquisas').document(pesquisa_id).get()
    if not pesquisa_doc.exists:
        raise HTTPException(status_code=404, detail="Pesquisa não encontrada")
    
    # Salvar respostas
    resposta_dict = {
        'pesquisa_id': pesquisa_id,
        'usuario_id': current_user.id,
        'negocio_id': negocio_id,
        'respostas': [r.model_dump() for r in resposta_data.respostas],
        'data_resposta': firestore.SERVER_TIMESTAMP
    }
    
    doc_ref = db.collection('respostas_pesquisas').document()
    doc_ref.set(resposta_dict)
    
    # Atualizar contador de respostas na pesquisa
    db.collection('pesquisas').document(pesquisa_id).update({
        'respostas_coletadas': firestore.Increment(1)
    })
    
    # Retornar pesquisa atualizada
    pesquisa_atualizada = db.collection('pesquisas').document(pesquisa_id).get()
    result = pesquisa_atualizada.to_dict()
    result['id'] = pesquisa_atualizada.id
    
    return result

@router.get("/negocios/{negocio_id}/pesquisas/resultados", response_model=List[schemas.PesquisaEnviadaResponse])
def obter_resultados_pesquisas(
    negocio_id: str = Depends(validate_path_negocio_id),
    modelo_pesquisa_id: Optional[str] = Query(None, description="Filtrar por modelo de pesquisa específico"),
    admin: schemas.UsuarioProfile = Depends(get_current_admin_user),
    db: firestore.client = Depends(get_db)
):
    """Obtém os resultados das pesquisas de satisfação."""
    return crud.listar_resultados_pesquisas(db, negocio_id, modelo_pesquisa_id)

# =================================================================================
# ENDPOINTS DE FLUXO DO TÉCNICO - CONFIRMAÇÕES
# =================================================================================

@router.post("/pacientes/{paciente_id}/confirmar-leitura-plano", response_model=schemas.ConfirmacaoLeituraResponse)
def confirmar_leitura_plano(
    paciente_id: str,
    confirmacao_data: schemas.ConfirmacaoLeituraCreate,
    current_user: schemas.UsuarioProfile = Depends(get_current_tecnico_user),
    db: firestore.client = Depends(get_db)
):
    """Confirma a leitura do plano de cuidados pelo técnico."""
    # Criar confirmação
    confirmacao_dict = {
        'paciente_id': paciente_id,
        'tecnico_id': current_user.id,
        'tecnico_nome': current_user.nome,
        'tipo': 'leitura_plano',
        'confirmado': True,
        'observacoes': confirmacao_data.observacoes,
        'data_confirmacao': firestore.SERVER_TIMESTAMP
    }
    
    doc_ref = db.collection('confirmacoes_leitura').document()
    doc_ref.set(confirmacao_dict)
    confirmacao_dict['id'] = doc_ref.id
    
    return confirmacao_dict

@router.get("/pacientes/{paciente_id}/verificar-leitura-plano")
def verificar_leitura_plano(
    paciente_id: str,
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """Verifica se o plano de cuidados foi lido pelo técnico."""
    query = db.collection('confirmacoes_leitura') \
             .where('paciente_id', '==', paciente_id) \
             .where('tipo', '==', 'leitura_plano') \
             .limit(1)
    
    docs = list(query.stream())
    
    return {
        "plano_lido": len(docs) > 0,
        "paciente_id": paciente_id,
        "data_verificacao": firestore.SERVER_TIMESTAMP
    }

@router.post("/pacientes/{paciente_id}/confirmar-leitura", response_model=schemas.ConfirmacaoLeituraResponse)
def confirmar_leitura_geral(
    paciente_id: str,
    confirmacao_data: schemas.ConfirmacaoLeituraCreate,
    current_user: schemas.UsuarioProfile = Depends(get_current_tecnico_user),
    db: firestore.client = Depends(get_db)
):
    """Confirma leitura geral de documentos/informações."""
    # Criar confirmação genérica
    confirmacao_dict = {
        'paciente_id': paciente_id,
        'tecnico_id': current_user.id,
        'tecnico_nome': current_user.nome,
        'tipo': 'leitura_geral',
        'confirmado': True,
        'observacoes': confirmacao_data.observacoes,
        'data_confirmacao': firestore.SERVER_TIMESTAMP
    }
    
    doc_ref = db.collection('confirmacoes_leitura').document()
    doc_ref.set(confirmacao_dict)
    confirmacao_dict['id'] = doc_ref.id
    
    return confirmacao_dict

@router.get("/pacientes/{paciente_id}/confirmar-leitura/status")
def verificar_status_leitura(
    paciente_id: str,
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """Verifica o status de confirmação de leitura para um paciente."""
    query = db.collection('confirmacoes_leitura') \
             .where('paciente_id', '==', paciente_id) \
             .order_by('data_confirmacao', direction=firestore.Query.DESCENDING)
    
    confirmacoes = []
    for doc in query.stream():
        conf_data = doc.to_dict()
        conf_data['id'] = doc.id
        confirmacoes.append(conf_data)
    
    return {
        "paciente_id": paciente_id,
        "total_confirmacoes": len(confirmacoes),
        "ultima_confirmacao": confirmacoes[0] if confirmacoes else None,
        "confirmacoes": confirmacoes
    }