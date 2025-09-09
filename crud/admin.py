# crud/admin.py
"""
CRUD para funções administrativas
"""

import logging
from typing import Optional, List, Dict
from firebase_admin import firestore, auth
import schemas
from .utils import (
    decrypt_user_sensitive_fields,
    add_timestamps
)
from .usuarios import buscar_usuario_por_firebase_uid, criar_ou_atualizar_usuario
from .profissionais import buscar_profissional_por_uid, criar_profissional
from .pacientes import atualizar_endereco_paciente
from crypto_utils import decrypt_data

logger = logging.getLogger(__name__)

USER_SENSITIVE_FIELDS = ['nome', 'telefone']


def check_admin_status(db: firestore.client, negocio_id: str) -> bool:
    """Verifica se um negócio já possui um administrador."""
    try:
        negocio_doc = db.collection('negocios').document(negocio_id).get()
        if negocio_doc.exists:
            negocio_data = negocio_doc.to_dict()
            return negocio_data.get('admin_uid') is not None
        return False
    except Exception as e:
        logger.error(f"Erro ao verificar status do admin para o negócio {negocio_id}: {e}")
        return False


def admin_listar_usuarios_por_negocio(db: firestore.client, negocio_id: str, status: str = 'ativo') -> List[Dict]:
    """Lista todos os usuários de um negócio (lógica simplificada do backup)."""
    usuarios = []
    try:
        query = db.collection('usuarios').where(f'roles.{negocio_id}', 'in', ['cliente', 'profissional', 'admin', 'tecnico', 'medico'])
        
        for doc in query.stream():
            usuario_data = doc.to_dict()
            status_no_negocio = usuario_data.get('status_por_negocio', {}).get(negocio_id, 'ativo')
            
            if status == 'all' or status_no_negocio == status:
                usuario_data['id'] = doc.id
                usuario_data = decrypt_user_sensitive_fields(usuario_data, USER_SENSITIVE_FIELDS)
                usuarios.append(usuario_data)
        
        logger.info(f"Retornando {len(usuarios)} usuários para o negócio {negocio_id} com status {status}")
        return usuarios
    except Exception as e:
        logger.error(f"Erro ao listar usuários do negócio {negocio_id}: {e}")
        return []


def admin_set_usuario_status(db: firestore.client, negocio_id: str, user_id: str, status: str, autor_uid: str) -> Optional[Dict]:
    """Define o status de um usuário ('ativo' ou 'inativo') em um negócio."""
    if status not in ['ativo', 'inativo']:
        raise ValueError("Status inválido. Use 'ativo' ou 'inativo'.")
    user_ref = db.collection('usuarios').document(user_id)
    user_doc = user_ref.get()
    
    if not user_doc.exists:
        return None
    
    user_ref.update({f'status_por_negocio.{negocio_id}': status})
    
    updated_doc = user_ref.get()
    updated_data = updated_doc.to_dict()
    updated_data['id'] = updated_doc.id
    
    return decrypt_user_sensitive_fields(updated_data, USER_SENSITIVE_FIELDS)


def admin_atualizar_role_usuario(db: firestore.client, negocio_id: str, user_id: str, novo_role: str, autor_uid: str) -> Optional[Dict]:
    """Atualiza o role de um usuário e gerencia o perfil profissional (lógica do backup)."""
    if novo_role not in ['cliente', 'profissional', 'admin', 'tecnico', 'medico']:
        raise ValueError("Role inválida.")
    
    user_ref = db.collection('usuarios').document(user_id)
    user_doc = user_ref.get()

    if not user_doc.exists: return None
    user_data = user_doc.to_dict()

    if negocio_id not in user_data.get("roles", {}): return None

    user_ref.update({f'roles.{negocio_id}': novo_role})
    
    perfil_profissional = buscar_profissional_por_uid(db, negocio_id, user_data['firebase_uid'])
    
    if novo_role in ['profissional', 'admin']:
        if not perfil_profissional:
            # Descriptografa o nome antes de passar para a criação do perfil
            nome_descriptografado = decrypt_data(user_data.get('nome', ''))
            criar_profissional(db, schemas.ProfissionalCreate(
                negocio_id=negocio_id, usuario_uid=user_data['firebase_uid'],
                nome=nome_descriptografado, ativo=True, fotos={}
            ))
        elif not perfil_profissional.get('ativo'):
            db.collection('profissionais').document(perfil_profissional['id']).update({"ativo": True})
    elif novo_role in ['cliente', 'tecnico', 'medico']:
        if perfil_profissional and perfil_profissional.get('ativo'):
            db.collection('profissionais').document(perfil_profissional['id']).update({"ativo": False})

    updated_doc = user_ref.get()
    updated_data = updated_doc.to_dict()
    updated_data['id'] = updated_doc.id
    return decrypt_user_sensitive_fields(updated_data, USER_SENSITIVE_FIELDS)


def admin_criar_paciente(db: firestore.client, negocio_id: str, paciente_data: schemas.PacienteCreateByAdmin) -> Dict:
    """Cria um novo paciente (lógica do backup)."""
    try:
        firebase_user = auth.create_user(
            email=paciente_data.email,
            password=paciente_data.password,
            display_name=paciente_data.nome
        )
    except auth.EmailAlreadyExistsError:
        raise ValueError(f"O e-mail {paciente_data.email} já está em uso.")
    except Exception as e:
        raise e

    sync_data = schemas.UsuarioSync(
        nome=paciente_data.nome,
        email=paciente_data.email,
        firebase_uid=firebase_user.uid,
        negocio_id=negocio_id,
        telefone=paciente_data.telefone
    )

    try:
        user_profile = criar_ou_atualizar_usuario(db, sync_data)
        
        if paciente_data.endereco:
            atualizar_endereco_paciente(db, user_profile['id'], paciente_data.endereco)
            user_profile['endereco'] = paciente_data.endereco.model_dump()
        
        dados_pessoais_update = paciente_data.model_dump(exclude={'email', 'password', 'nome', 'telefone', 'endereco'}, exclude_unset=True)
        if dados_pessoais_update:
            db.collection('usuarios').document(user_profile['id']).update(dados_pessoais_update)
            user_profile.update(dados_pessoais_update)

        return user_profile
    except Exception as e:
        auth.delete_user(firebase_user.uid)
        raise e

def admin_listar_clientes_por_negocio(db: firestore.client, negocio_id: str, status: str = 'ativo') -> List[Dict]:
    """Lista todos os clientes de um negócio específico (lógica do backup)."""
    all_users = admin_listar_usuarios_por_negocio(db, negocio_id, status)
    return [user for user in all_users if user.get('roles', {}).get(negocio_id) == 'cliente']