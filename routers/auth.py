# routers/auth.py
"""
Router para autenticação e gestão de usuários
"""

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Body, Form
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
import json

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