# auth.py (Versão para Firestore com Super-Admin)

from fastapi import Depends, HTTPException, status, Header
from fastapi.security import OAuth2PasswordBearer
from firebase_admin import auth
import schemas
import crud
from database import get_db
from typing import Optional

# O OAuth2PasswordBearer ainda pode ser útil para a documentação interativa (botão "Authorize")
# mas a lógica de validação de token agora é 100% via Firebase ID Token.
# A tokenUrl "login" não existe mais como um endpoint de usuário/senha.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_current_user_firebase(token: str = Depends(oauth2_scheme), db = Depends(get_db)) -> schemas.UsuarioProfile:
    """
    Decodifica o ID Token do Firebase, busca o usuário correspondente no Firestore
    e retorna seu perfil como um schema Pydantic.
    """
    try:
        decoded_token = auth.verify_id_token(token)
        firebase_uid = decoded_token['uid']
    except Exception as e:
        # Log do erro pode ser útil aqui para depuração
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token inválido ou expirado: {e}"
        )

    # A função crud.buscar_usuario_por_firebase_uid será reescrita para usar o cliente 'db' do Firestore
    usuario_doc = crud.buscar_usuario_por_firebase_uid(db, firebase_uid=firebase_uid)
    
    if not usuario_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Perfil de usuário não encontrado em nosso sistema."
        )
    
    # Converte o dicionário/documento do Firestore para o nosso modelo Pydantic
    return schemas.UsuarioProfile(**usuario_doc)


def get_current_admin_user(
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    negocio_id: Optional[str] = Header(None, description="ID do Negócio para o qual a permissão de admin é necessária")
) -> schemas.UsuarioProfile:
    """
    Verifica se o usuário atual é o administrador do negócio especificado no header.
    Esta função é a dependência de segurança para endpoints de gerenciamento de negócio.
    """
    if not negocio_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O header 'negocio-id' é obrigatório para esta operação."
        )

    # Verifica se o usuário tem a role 'admin' para o negocio_id específico
    if current_user.roles.get(negocio_id) != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado: você não é o administrador deste negócio."
        )
    return current_user


# --- NOVA FUNÇÃO DE SEGURANÇA PARA O SUPER-ADMIN ---
def get_super_admin_user(current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase)) -> schemas.UsuarioProfile:
    """
    Verifica se o usuário atual tem a permissão de super_admin da plataforma.
    """
    if current_user.roles.get("platform") != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado: esta operação requer privilégios de Super Administrador."
        )
    return current_user

# --- FUNÇÃO QUE ESTAVA FALTANDO ---
def get_current_profissional_user(
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    negocio_id: Optional[str] = Header(None, description="ID do Negócio no qual o profissional está atuando")
) -> schemas.UsuarioProfile:
    """
    Verifica se o usuário atual é um profissional do negócio especificado no header.
    Esta função é a dependência de segurança para endpoints de autogestão do profissional.
    """
    if not negocio_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O header 'negocio-id' é obrigatório para esta operação."
        )

    # Verifica se o usuário tem a role 'profissional' OU 'admin' (pois um admin também é um profissional)
    user_role_for_negocio = current_user.roles.get(negocio_id)
    if user_role_for_negocio not in ["profissional", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado: você não é um profissional deste negócio."
        )
    return current_user