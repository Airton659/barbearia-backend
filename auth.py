# auth.py (Versão Corrigida)

from fastapi import Depends, HTTPException, status, Header, Path
from fastapi.security import OAuth2PasswordBearer
from firebase_admin import auth
import schemas
import crud
from database import get_db
from typing import Optional, Dict

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
    Super Admin tem acesso a todos os negócios.
    """
    # Se for super_admin, permite o acesso a qualquer negócio
    if current_user.roles.get("platform") == "super_admin":
        return negocio_id

    if negocio_id not in current_user.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado: você não tem permissão para acessar este negócio."
        )
    return negocio_id


# Em auth.py

def validate_path_negocio_id(
    negocio_id: str = Path(..., description="ID do negócio a ser validado."),
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase)
):
    """
    Valida o acesso ao negócio. O Super Admin tem acesso a todos.
    """
    # Se for super_admin, permite o acesso
    if current_user.roles.get("platform") == "super_admin":
        return negocio_id

    # Senão, verifica a permissão específica do negócio
    if negocio_id not in current_user.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado: você não tem permissão para acessar este negócio."
        )
    return negocio_id


def get_current_admin_user(
    negocio_id: str, 
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase)
) -> schemas.UsuarioProfile:
    """
    Verifica se o usuário é o Super Admin OU o admin do negócio.
    """
    # Se for super_admin, permite o acesso
    if current_user.roles.get("platform") == "super_admin":
        return current_user

    # Senão, verifica se é admin do negócio
    if current_user.roles.get(negocio_id) != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado: você não é o administrador deste negócio."
        )
    return current_user


def get_current_admin_or_profissional_user(
    negocio_id: str,
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase)
) -> schemas.UsuarioProfile:
    """
    Verifica se o usuário é o Super Admin, OU um admin, OU um profissional do negócio.
    """
    # Se for super_admin, permite o acesso
    if current_user.roles.get("platform") == "super_admin":
        return current_user

    # Senão, verifica as outras permissões
    user_role = current_user.roles.get(negocio_id)
    if user_role not in ["admin", "profissional"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado: você não tem permissão de Gestor ou Enfermeiro para esta operação."
        )
    return current_user
# --- FIM DO NOVO BLOCO DE CÓDIGO ---


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
    Super Admin tem acesso total.
    Esta função é a dependência de segurança para endpoints de autogestão do profissional.
    """
    if not negocio_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O header 'negocio-id' é obrigatório para esta operação."
        )

    # Super Admin tem acesso total
    if current_user.roles.get("platform") == "super_admin":
        return current_user

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

def get_paciente_autorizado(
    paciente_id: str = Path(..., description="ID do paciente cujos dados estão sendo acessados."),
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db = Depends(get_db)
) -> schemas.UsuarioProfile:
    """
    Dependência de segurança para garantir que o usuário atual tem permissão
    para acessar ou modificar os dados de um paciente específico.
    Super Admin tem acesso total.
    """
    print("--- INICIANDO VERIFICAÇÃO DE ACESSO AO PACIENTE ---")
    print(f"ID do Paciente alvo: {paciente_id}")
    print(f"ID do Usuário tentando acessar: {current_user.id}")
    print(f"Roles do Usuário: {current_user.roles}")

    # 0. Super Admin tem acesso total a todos os pacientes
    if current_user.roles.get("platform") == "super_admin":
        print("DEBUG: Acesso permitido. Usuário é Super Admin.")
        return current_user

    # 1. O próprio paciente sempre tem acesso.
    if current_user.id == paciente_id:
        print("DEBUG: Acesso permitido. Usuário é o próprio paciente.")
        return current_user

    # Busca o documento completo do paciente para obter os vínculos
    paciente_doc_ref = db.collection('usuarios').document(paciente_id)
    paciente_doc = paciente_doc_ref.get()
    if not paciente_doc.exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paciente não encontrado.")
    
    paciente_data = paciente_doc.to_dict()
    print(f"Dados do Paciente no DB: {paciente_data}")
    
    # Extrai o negocio_id do paciente
    negocio_id_paciente = list(paciente_data.get('roles', {}).keys())[0] if paciente_data.get('roles') else None
    if not negocio_id_paciente:
         raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Paciente não está associado a uma clínica.")

    # 2. O Gestor (admin) da clínica do paciente tem acesso.
    if current_user.roles.get(negocio_id_paciente) == 'admin':
        print("DEBUG: Acesso permitido. Usuário é admin da clínica.")
        return current_user
        
    # 3. O Enfermeiro vinculado ao paciente tem acesso.
    enfermeiro_vinculado_id = paciente_data.get('enfermeiro_id')
    if enfermeiro_vinculado_id and current_user.id == enfermeiro_vinculado_id:
        print("DEBUG: Acesso permitido. Usuário é o enfermeiro vinculado.")
        return current_user

    # --- INÍCIO DA CORREÇÃO ---
    # 4. O Técnico vinculado ao paciente tem acesso.
    tecnicos_vinculados_ids = paciente_data.get('tecnicos_ids', [])
    if current_user.id in tecnicos_vinculados_ids:
        print("DEBUG: Acesso permitido. Usuário é um técnico vinculado.")
        return current_user
    # --- FIM DA CORREÇÃO ---

    # Se nenhuma das condições for atendida, nega o acesso.
    print("--- ACESSO NEGADO. Nenhuma regra de permissão foi atendida. ---")
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Acesso negado: você não tem permissão para visualizar ou modificar os dados deste paciente."
    )

# --- NOVO BLOCO DE CÓDIGO AQUI ---
def get_current_tecnico_user(
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase)
) -> schemas.UsuarioProfile:
    """
    Verifica se o usuário atual tem a role 'tecnico' em algum dos negócios.
    Super Admin tem acesso total.
    Esta é uma verificação genérica; a lógica do endpoint deve validar o negócio específico.
    """
    # Super Admin tem acesso total
    if current_user.roles.get("platform") == "super_admin":
        return current_user

    # Extrai a primeira role 'tecnico' que encontrar para validação.
    # A validação de negócio específico acontecerá no endpoint.
    user_roles = current_user.roles
    is_tecnico_in_any_negocio = any(role == 'tecnico' for role in user_roles.values())

    if not is_tecnico_in_any_negocio:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado: você não tem a permissão de Técnico."
        )
    return current_user
# --- FIM DO NOVO BLOCO DE CÓDIGO ---


def get_current_admin_or_tecnico_user(
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase)
) -> schemas.UsuarioProfile:
    """
    Verifica se o usuário atual tem a role 'admin', 'profissional' ou 'tecnico' em algum dos negócios.
    Super Admin tem acesso total.
    Esta é uma verificação genérica; a lógica do endpoint deve validar o negócio específico.
    """
    # Super Admin tem acesso total
    if current_user.roles.get("platform") == "super_admin":
        return current_user

    # Verifica se tem alguma das roles permitidas
    user_roles = current_user.roles
    allowed_roles = ['admin', 'profissional', 'tecnico']
    has_allowed_role = any(role in allowed_roles for role in user_roles.values())

    if not has_allowed_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado: você não tem permissão de Admin, Profissional ou Técnico."
        )
    return current_user


# Em auth.py, adicione esta nova função no final do arquivo

def get_paciente_autorizado_anamnese(
    paciente_id: str = Path(..., description="ID do paciente cujos dados estão sendo acessados."),
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db = Depends(get_db)
) -> schemas.UsuarioProfile:
    """
    Dependência de segurança para Anamnese.
    Permite acesso ao próprio paciente, ao admin, ao enfermeiro vinculado, ou ao Super Admin.
    BLOQUEIA O ACESSO DE TÉCNICOS.
    """
    # 0. Super Admin tem acesso total
    if current_user.roles.get("platform") == "super_admin":
        return current_user

    # 1. O próprio paciente sempre tem acesso.
    if current_user.id == paciente_id:
        return current_user

    paciente_doc = db.collection('usuarios').document(paciente_id).get()
    if not paciente_doc.exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paciente não encontrado.")
    
    paciente_data = paciente_doc.to_dict()
    negocio_id_paciente = list(paciente_data.get('roles', {}).keys())[0] if paciente_data.get('roles') else None
    if not negocio_id_paciente:
         raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Paciente não está associado a uma clínica.")

    # 2. O Gestor (admin) da clínica do paciente tem acesso.
    if current_user.roles.get(negocio_id_paciente) == 'admin':
        return current_user
        
    # 3. O Enfermeiro vinculado ao paciente tem acesso.
    enfermeiro_vinculado_id = paciente_data.get('enfermeiro_id')
    if enfermeiro_vinculado_id and current_user.id == enfermeiro_vinculado_id:
        return current_user

    # 4. Nenhuma outra role (incluindo técnico) tem acesso.
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Acesso negado: seu perfil não tem permissão para visualizar ou modificar a Ficha de Avaliação."
    )

def get_current_medico_user(
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    # CORREÇÃO APLICADA AQUI:
    # O header 'negocio-id' foi definido como obrigatório, removendo a ambiguidade
    # de 'Optional[str]' e o default 'None'.
    negocio_id: str = Header(..., description="ID do Negócio no qual o médico está atuando")
) -> schemas.UsuarioProfile:
    """
    Verifica se o usuário atual tem a role 'medico' em algum dos negócios.
    Super Admin tem acesso total.
    """
    # Super Admin tem acesso total
    if current_user.roles.get("platform") == "super_admin":
        return current_user

    # Como o Header agora é obrigatório (definido com ...), o FastAPI garante que ele existe.
    # A verificação 'if not negocio_id:' pode ser removida para um código mais limpo.
    user_role_for_negocio = current_user.roles.get(negocio_id)
    if user_role_for_negocio != "medico":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado: você não tem a permissão de Médico para este negócio."
        )
    return current_user

def get_admin_or_profissional_autorizado_paciente(
    paciente_id: str = Path(..., description="ID do paciente cujos dados estão sendo modificados."),
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db = Depends(get_db)
) -> schemas.UsuarioProfile:
    """
    Dependência de segurança restritiva para operações de escrita no plano de cuidado.
    Permite acesso a administradores, profissionais (enfermeiros), ou Super Admin.
    BLOQUEIA O ACESSO DE TÉCNICOS para operações de escrita.
    """
    # 0. Super Admin tem acesso total
    if current_user.roles.get("platform") == "super_admin":
        return current_user

    # Busca o documento completo do paciente para obter o negócio
    paciente_doc_ref = db.collection('usuarios').document(paciente_id)
    paciente_doc = paciente_doc_ref.get()
    if not paciente_doc.exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paciente não encontrado.")

    paciente_data = paciente_doc.to_dict()

    # Extrai o negocio_id do paciente
    negocio_id_paciente = list(paciente_data.get('roles', {}).keys())[0] if paciente_data.get('roles') else None
    if not negocio_id_paciente:
         raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Paciente não está associado a uma clínica.")

    # Verifica se o usuário tem role de admin ou profissional no negócio do paciente
    user_role = current_user.roles.get(negocio_id_paciente)
    if user_role not in ["admin", "profissional"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado: apenas administradores e profissionais podem modificar o plano de cuidado."
        )

    return current_user

def get_relatorio_autorizado(
    relatorio_id: str = Path(..., description="ID do relatório a ser acessado."),
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db = Depends(get_db)
) -> Dict:
    """
    Dependência que busca um relatório e valida se o usuário atual tem permissão para acessá-lo.
    Permite acesso ao Admin/Profissional do negócio, ao Médico atribuído, ou ao Super Admin.
    Retorna o dicionário do relatório se autorizado.
    """
    import crud  # Import local para evitar dependência circular

    relatorio_doc = db.collection('relatorios_medicos').document(relatorio_id).get()
    if not relatorio_doc.exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Relatório não encontrado.")

    relatorio_data = relatorio_doc.to_dict()
    relatorio_data['id'] = relatorio_doc.id
    negocio_id = relatorio_data.get('negocio_id')
    medico_id = relatorio_data.get('medico_id')

    user_roles = current_user.roles

    # 0. Super Admin tem acesso total
    if user_roles.get("platform") == "super_admin":
        # Popula o criado_por antes de retornar
        return crud._popular_criado_por(db, relatorio_data)

    # 1. Admin ou Profissional do negócio têm acesso
    if user_roles.get(negocio_id) in ['admin', 'profissional']:
        # Popula o criado_por antes de retornar
        return crud._popular_criado_por(db, relatorio_data)

    # 2. O médico atribuído ao relatório tem acesso
    if user_roles.get(negocio_id) == 'medico' and current_user.id == medico_id:
        # Popula o criado_por antes de retornar
        return crud._popular_criado_por(db, relatorio_data)

    # 3. Nega o acesso para todos os outros casos
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Acesso negado: você não tem permissão para visualizar este relatório."
    )