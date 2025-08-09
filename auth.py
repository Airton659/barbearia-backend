# auth.py (Versão para Firestore)

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from firebase_admin import auth
import schemas
import crud
from database import get_db

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


def get_current_admin_user(current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase)) -> schemas.UsuarioProfile:
    """
    Verifica se o usuário atual (já validado e carregado do Firestore)
    tem uma role de 'admin' em algum dos negócios.
    
    NOTA: A lógica de "admin" pode precisar ser refinada no modelo multi-tenant.
    Por exemplo, ser admin de um negócio específico. Por enquanto, mantemos a verificação genérica.
    """
    # A verificação de "tipo" pode ser ajustada para o novo modelo de "roles"
    # Ex: if "admin" in current_user.roles.values():
    if "admin" not in current_user.roles.values():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado: esta operação requer privilégios de administrador."
        )
    return current_user