# routers/auth.py
"""
Router para autenticação e gestão de usuários
"""

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.security import OAuth2PasswordBearer
from typing import Optional
import schemas
import crud
from database import get_db
from auth import get_current_user_firebase, get_optional_current_user_firebase
from firebase_admin import firestore, auth
import logging
import uuid
import os

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Usuários"])

@router.post("/users/sync-profile", response_model=schemas.UsuarioProfile)
def sync_profile(
    user_data: schemas.UsuarioSync,
    db: firestore.client = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    """
    Sincroniza o perfil do usuário autenticado via Firebase.
    Se é a primeira vez, cria o usuário. Se já existe, retorna os dados atualizados.
    """
    try:
        # Validar o token Firebase primeiro
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token de autenticação não fornecido."
            )
        
        try:
            decoded_token = auth.verify_id_token(token)
            firebase_uid_token = decoded_token['uid']
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Token inválido ou expirado: {e}"
            )
        
        # Verificar se o firebase_uid do token corresponde ao enviado nos dados
        if firebase_uid_token != user_data.firebase_uid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Firebase UID no token não corresponde aos dados enviados."
            )
        
        # LOG CRÍTICO: Rastrear se este endpoint está sendo chamado
        logger.critical(f"🚨 SYNC-PROFILE CHAMADO - firebase_uid: {user_data.firebase_uid}, email: {user_data.email}")
        
        # Usar a função CRUD atualizada que já maneja toda a lógica
        usuario = crud.criar_ou_atualizar_usuario(db, user_data)
        logger.info(f"Perfil sincronizado para o usuário {usuario.get('email', 'N/A')}")
        return usuario
        
    except ValueError as ve:
        logger.warning(f"Erro de validação na sincronização: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Erro inesperado na sincronização: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno do servidor: {str(e)}")

@router.get("/me/profile", response_model=schemas.UsuarioProfile)
def get_my_profile(current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase)):
    """Retorna o perfil completo do usuário autenticado."""
    return current_user

@router.post("/me/register-fcm-token", status_code=status.HTTP_200_OK)
def registrar_fcm_token(
    token_data: schemas.FCMTokenRequest,
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """Registra um token FCM para o usuário autenticado."""
    crud.adicionar_fcm_token(db, current_user.firebase_uid, token_data.fcm_token)
    return {"message": "Token FCM registrado com sucesso"}

@router.put("/users/update-profile", response_model=schemas.UserProfileUpdateResponse)
async def update_user_profile(
    update_data: schemas.UserProfileUpdate,
    profile_image: Optional[UploadFile] = File(None),
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """
    Atualiza o perfil do usuário com dados pessoais e imagem de perfil.
    """
    try:
        # LOG CRÍTICO: Rastrear exatamente qual usuário está sendo processado
        logger.critical(f"✅ UPDATE-PROFILE CHAMADO - firebase_uid: {current_user.firebase_uid}, user_id: {current_user.id}, roles: {current_user.roles}")
        
        profile_image_url = None
        
        # Processar imagem se fornecida
        if profile_image:
            # Verificar tipo de arquivo
            allowed_types = ["image/jpeg", "image/png", "image/jpg"]
            if profile_image.content_type not in allowed_types:
                raise HTTPException(
                    status_code=400,
                    detail="Tipo de arquivo não suportado. Use apenas JPEG, PNG ou JPG."
                )
            
            # Verificar tamanho do arquivo (max 5MB)
            if profile_image.size and profile_image.size > 5 * 1024 * 1024:
                raise HTTPException(
                    status_code=400,
                    detail="Arquivo muito grande. Máximo 5MB."
                )
            
            # Gerar nome único para o arquivo
            file_extension = profile_image.filename.split('.')[-1] if profile_image.filename else 'jpg'
            unique_filename = f"{current_user.id}_{uuid.uuid4()}.{file_extension}"
            
            # Criar diretório se não existir
            upload_dir = os.path.join("uploads", "profiles")
            os.makedirs(upload_dir, exist_ok=True)
            
            # Salvar arquivo
            file_path = os.path.join(upload_dir, unique_filename)
            with open(file_path, "wb") as buffer:
                content = await profile_image.read()
                buffer.write(content)
            
            # URL para acesso ao arquivo
            profile_image_url = f"/uploads/profiles/{unique_filename}"
            logger.info(f"Imagem de perfil salva: {profile_image_url}")
        
        # Buscar negocio_id do usuário atual
        negocio_id = None
        user_roles = current_user.roles or {}
        
        # Pegar o primeiro negócio que não seja 'platform'
        for biz_id, role in user_roles.items():
            if biz_id != 'platform':
                negocio_id = biz_id
                break
        
        if not negocio_id:
            raise HTTPException(
                status_code=400,
                detail="Usuário não está associado a nenhum negócio válido"
            )
        
        # Atualizar perfil usando a função CRUD
        updated_user = crud.atualizar_perfil_usuario(
            db, current_user.id, negocio_id, update_data, profile_image_url
        )
        
        if not updated_user:
            raise HTTPException(
                status_code=404,
                detail="Não foi possível atualizar o perfil do usuário"
            )
        
        return {
            "message": "Perfil atualizado com sucesso",
            "usuario": updated_user,
            "profile_image_url": profile_image_url
        }
        
    except ValueError as ve:
        logger.warning(f"Erro de validação na atualização do perfil: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Erro ao atualizar perfil do usuário {current_user.id}: {e}")
        raise HTTPException(status_code=500, detail="Erro interno do servidor")

@router.patch("/me/consent", response_model=schemas.UsuarioProfile)
def atualizar_meu_consentimento_lgpd(
    consent_data: schemas.ConsentimentoLGPDUpdate,
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """Atualiza o consentimento LGPD do usuário autenticado."""
    result = crud.atualizar_consentimento_lgpd(db, current_user.id, consent_data)
    if not result:
        raise HTTPException(status_code=404, detail="Não foi possível atualizar o consentimento")
    return result