from datetime import datetime, timedelta
from typing import Optional
import json
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
import crud, models, schemas
import os
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, auth
from database import get_db
from google.cloud import secretmanager

load_dotenv()

# --- Configuração do Firebase Admin SDK via Secret Manager ---
# Verifica se o SDK já foi inicializado para evitar erros
if not firebase_admin._apps:
    try:
        # ID do seu projeto Google Cloud
        project_id = "barbearia-backend-gc" 
        # Nome do secret que foi criado
        secret_id = "firebase-admin-credentials" 
        version_id = "latest"

        # Cria o cliente do Secret Manager
        client = secretmanager.SecretManagerServiceClient()

        # Monta o nome completo do recurso do secret
        name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"

        # Acessa a versão do secret
        response = client.access_secret_version(request={"name": name})

        # Decodifica o payload (o conteúdo do secret) para uma string
        payload = response.payload.data.decode("UTF-8")
        
        # Converte a string JSON para um dicionário
        cred_json = json.loads(payload)

        # Inicializa o Firebase com as credenciais do Secret Manager
        cred = credentials.Certificate(cred_json)
        firebase_admin.initialize_app(cred)
        print("Firebase Admin SDK inicializado com sucesso via Secret Manager.")

    except Exception as e:
        print(f"ERRO CRÍTICO ao inicializar o Firebase via Secret Manager: {e}")
        # Levantar a exceção para que o container não inicie se o Firebase falhar
        raise e


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def get_current_user_firebase(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> models.Usuario:
    """
    Decodifica o ID Token do Firebase e busca o usuário correspondente no nosso banco de dados.
    """
    try:
        decoded_token = auth.verify_id_token(token)
        firebase_uid = decoded_token['uid']
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Token inválido ou expirado: {e}")

    usuario = crud.buscar_usuario_por_firebase_uid(db, firebase_uid=firebase_uid)
    if not usuario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Perfil de usuário não encontrado em nosso sistema.")
    return usuario


def get_current_admin_user(current_user: models.Usuario = Depends(get_current_user_firebase)) -> models.Usuario:
    """
    Verifica se o usuário atual é um administrador.
    """
    if current_user.tipo != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado: esta operação requer privilégios de administrador."
        )
    return current_user