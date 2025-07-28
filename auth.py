from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
import crud, models, schemas
import os
from dotenv import load_dotenv
# Alteração 1: Importar a função get_db do módulo de banco de dados
from database import get_db

load_dotenv()

# Configurações do token
SECRET_KEY = os.getenv("SECRET_KEY", "chave_secreta_fallback")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


# ---------- Gerar token ----------
def criar_token(dados: dict, expires_delta: Optional[timedelta] = None):
    to_encode = dados.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# ---------- Verificar token ----------
def verificar_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        usuario_id: str = payload.get("sub")
        if usuario_id is None:
            raise HTTPException(status_code=401, detail="Token inválido")
        return usuario_id
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido")


# ---------- Dependência ----------
# Alteração 2: Corrigido para usar a dependência get_db centralizada
def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> models.Usuario:
    usuario_id = verificar_token(token)
    # Tenta converter o usuario_id para UUID para fazer a busca correta
    try:
        from uuid import UUID
        uid = UUID(usuario_id)
    except ValueError:
        raise HTTPException(status_code=401, detail="ID de usuário inválido no token")
    
    usuario = db.query(models.Usuario).filter(models.Usuario.id == uid).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return usuario

# --- NOVA FUNÇÃO DE DEPENDÊNCIA ADICIONADA ---

def get_current_admin_user(current_user: models.Usuario = Depends(get_current_user)) -> models.Usuario:
    """
    Verifica se o usuário atual é um administrador.
    Se não for, lança uma exceção HTTP 403 (Forbidden).
    """
    if current_user.tipo != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado: esta operação requer privilégios de administrador."
        )
    return current_user
