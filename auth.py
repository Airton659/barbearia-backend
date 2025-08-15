# auth.py (Versão Corrigida)

from fastapi import Depends, HTTPException, status, Header, Path
from fastapi.security import OAuth2PasswordBearer
from firebase_admin import auth
import schemas
import crud
from database import get_db
from typing import Optional

# O OAuth2PasswordBearer ainda pode ser útil para a documentação interativa (botão "Authorize")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False) # auto_error=False é importante para dependências opcionais

def get_current_user_firebase(token: str = Depends(oauth2_scheme), db = Depends(get_db)) -> schemas.UsuarioProfile:
    """
    Decodifica o ID Token do Firebase, busca o usuário correspondente no Firestore
    e retorna seu perfil como um schema Pydantic.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticação não fornecido."
        )
    try:
        decoded_token = auth.verify_id_token(token)
        firebase_uid = decoded_token['uid']
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token inválido ou expirado: {e}"
        )

    usuario_doc = crud.buscar_usuario_por_firebase_uid(db, firebase_uid=firebase_uid)
    
    if not usuario_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Perfil de usuário não encontrado em nosso sistema."
        )
    
    usuario_doc['profissional_id'] = None # Garante que o campo sempre exista

    # Se o usuário tiver roles, verifica se alguma é de profissional ou admin
    if usuario_doc.get('roles'):
        for negocio_id, role in usuario_doc['roles'].items():
            if role in ['admin', 'profissional']:
                # Busca o perfil profissional vinculado ao UID do usuário e ao negócio
                perfil_profissional = crud.buscar_profissional_por_uid(db, negocio_id, firebase_uid)
                if perfil_profissional:
                    usuario_doc['profissional_id'] = perfil_profissional.get('id')
                    # Interrompe o loop assim que encontrar o primeiro perfil
                    # para evitar sobreposições desnecessárias.
                    break
    
    return schemas.UsuarioProfile(**usuario_doc)


def validate_negocio_id(
    negocio_id: str = Header(..., description="ID do Negócio a ser validado."),
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase)
):
    """
    Valida se o usuário tem permissão para acessar o negócio especificado.
    """
    if negocio_id not in current_user.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado: você não tem permissão para acessar este negócio."
        )
    return negocio_id


def get_current_admin_user(
    # A MUDANÇA ESTÁ AQUI: FastAPI irá injetar o 'negocio_id' da URL (Path) diretamente.
    negocio_id: str, 
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase)
) -> schemas.UsuarioProfile:
    """
    Verifica se o usuário atual é o administrador do negócio especificado na URL.
    Esta função é a dependência de segurança para endpoints de gerenciamento de negócio.
    """
    # A verificação de `negocio_id` nulo não é mais necessária, pois um path param é sempre obrigatório.
    
    # Verifica se o usuário tem a role 'admin' para o negocio_id específico
    if current_user.roles.get(negocio_id) != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado: você não é o administrador deste negócio."
        )
    return current_user


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

def get_optional_current_user_firebase(
    token: Optional[str] = Depends(oauth2_scheme), db = Depends(get_db)
) -> Optional[schemas.UsuarioProfile]:
    """
    Tenta obter o usuário atual se um token for fornecido, mas não lança erro se não for.
    Retorna o perfil do usuário ou None.
    """
    if not token:
        return None
    try:
        # Reutiliza a lógica principal de obtenção e enriquecimento do usuário
        return get_current_user_firebase(token, db)
    except HTTPException:
        # Se get_current_user_firebase lançar uma exceção (token inválido/expirado, etc.),
        # nós a capturamos e retornamos None, tratando o usuário como anônimo.
        return None