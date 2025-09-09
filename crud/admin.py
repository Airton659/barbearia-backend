# crud/admin.py
"""
CRUD para funções administrativas
"""

import logging
from typing import Optional, List, Dict
from firebase_admin import firestore
import schemas
from crud.utils import (
    decrypt_user_sensitive_fields,
    encrypt_user_sensitive_fields,
    add_timestamps
)

logger = logging.getLogger(__name__)

# Campos sensíveis que precisam de criptografia
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
    """Lista todos os usuários de um negócio específico com um status específico."""
    usuarios = []
    try:
        query = db.collection('usuarios').where(f'roles.{negocio_id}', '!=', None)
        
        for doc in query.stream():
            usuario_data = doc.to_dict()
            
            # Verificar se o usuário tem o status correto neste negócio
            status_por_negocio = usuario_data.get('status_por_negocio', {})
            user_status = status_por_negocio.get(negocio_id, 'ativo')  # Default: ativo
            
            if user_status == status:
                usuario_data['id'] = doc.id
                
                # Descriptografar campos sensíveis
                usuario_data = decrypt_user_sensitive_fields(usuario_data, USER_SENSITIVE_FIELDS)
                
                usuarios.append(usuario_data)
        
        logger.info(f"Retornando {len(usuarios)} usuários para o negócio {negocio_id} com status {status}")
        return usuarios
    except Exception as e:
        logger.error(f"Erro ao listar usuários do negócio {negocio_id}: {e}")
        return []


def admin_set_usuario_status(db: firestore.client, negocio_id: str, user_id: str, status: str, autor_uid: str) -> Optional[Dict]:
    """Define o status de um usuário em um negócio específico."""
    try:
        user_ref = db.collection('usuarios').document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            logger.warning(f"Usuário {user_id} não encontrado")
            return None
        
        user_data = user_doc.to_dict()
        
        # Verificar se o usuário pertence ao negócio
        if negocio_id not in user_data.get('roles', {}):
            logger.warning(f"Usuário {user_id} não pertence ao negócio {negocio_id}")
            return None
        
        # Atualizar o status
        user_ref.update({
            f'status_por_negocio.{negocio_id}': status,
            'updated_at': firestore.SERVER_TIMESTAMP
        })
        
        logger.info(f"Status do usuário {user_id} alterado para {status} no negócio {negocio_id} pelo admin {autor_uid}")
        
        # Retornar dados atualizados
        updated_doc = user_ref.get()
        updated_data = updated_doc.to_dict()
        updated_data['id'] = updated_doc.id
        
        # Descriptografar campos sensíveis
        updated_data = decrypt_user_sensitive_fields(updated_data, USER_SENSITIVE_FIELDS)
        
        return updated_data
        
    except Exception as e:
        logger.error(f"Erro ao alterar status do usuário {user_id}: {e}")
        return None


def admin_atualizar_role_usuario(db: firestore.client, negocio_id: str, user_id: str, novo_role: str, autor_uid: str) -> Optional[Dict]:
    """Atualiza o role de um usuário em um negócio específico."""
    try:
        user_ref = db.collection('usuarios').document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            logger.warning(f"Usuário {user_id} não encontrado")
            return None
        
        user_data = user_doc.to_dict()
        
        # Verificar se o usuário pertence ao negócio
        if negocio_id not in user_data.get('roles', {}):
            logger.warning(f"Usuário {user_id} não pertence ao negócio {negocio_id}")
            return None
        
        # Atualizar o role
        user_ref.update({
            f'roles.{negocio_id}': novo_role,
            'updated_at': firestore.SERVER_TIMESTAMP
        })
        
        logger.info(f"Role do usuário {user_id} alterado para {novo_role} no negócio {negocio_id} pelo admin {autor_uid}")
        
        # Retornar dados atualizados
        updated_doc = user_ref.get()
        updated_data = updated_doc.to_dict()
        updated_data['id'] = updated_doc.id
        
        # Descriptografar campos sensíveis
        updated_data = decrypt_user_sensitive_fields(updated_data, USER_SENSITIVE_FIELDS)
        
        return updated_data
        
    except Exception as e:
        logger.error(f"Erro ao alterar role do usuário {user_id}: {e}")
        return None


def admin_criar_paciente(db: firestore.client, negocio_id: str, paciente_data: schemas.PacienteCreateByAdmin) -> Dict:
    """Cria um novo paciente via interface administrativa."""
    try:
        # Criptografar dados sensíveis
        dados_para_criptografar = {
            'nome': paciente_data.nome,
            'telefone': paciente_data.telefone
        }
        dados_criptografados = encrypt_user_sensitive_fields(dados_para_criptografar, USER_SENSITIVE_FIELDS)
        
        # Preparar dados do usuário
        user_dict = {
            "nome": dados_criptografados['nome'],
            "email": paciente_data.email,
            "firebase_uid": None,  # Será preenchido quando o usuário fizer login
            "roles": {negocio_id: "cliente"},
            "fcm_tokens": [],
            "status_por_negocio": {negocio_id: "ativo"}
        }
        
        # Adicionar telefone se fornecido
        if dados_criptografados['telefone']:
            user_dict['telefone'] = dados_criptografados['telefone']
        
        # Adicionar endereço se fornecido
        if paciente_data.endereco:
            from crud.utils import encrypt_endereco_fields
            user_dict['endereco'] = encrypt_endereco_fields(paciente_data.endereco.model_dump())
        
        # Adicionar dados pessoais básicos se fornecidos
        if paciente_data.data_nascimento:
            user_dict['data_nascimento'] = paciente_data.data_nascimento
        if paciente_data.sexo:
            user_dict['sexo'] = paciente_data.sexo
        if paciente_data.estado_civil:
            user_dict['estado_civil'] = paciente_data.estado_civil
        if paciente_data.profissao:
            user_dict['profissao'] = paciente_data.profissao
        
        # Adicionar timestamps
        user_dict = add_timestamps(user_dict, is_update=False)
        
        # Salvar no Firestore
        doc_ref = db.collection('usuarios').document()
        doc_ref.set(user_dict)
        user_dict['id'] = doc_ref.id
        
        logger.info(f"Paciente {paciente_data.email} criado via admin para o negócio {negocio_id}")
        
        # Descriptografar dados para resposta
        user_dict = decrypt_user_sensitive_fields(user_dict, USER_SENSITIVE_FIELDS)
        
        return user_dict
        
    except Exception as e:
        logger.error(f"Erro ao criar paciente via admin: {e}")
        raise


def admin_listar_clientes_por_negocio(db: firestore.client, negocio_id: str, status: str = 'ativo') -> List[Dict]:
    """Lista todos os clientes de um negócio específico."""
    clientes = []
    try:
        query = db.collection('usuarios').where(f'roles.{negocio_id}', '==', 'cliente')
        
        for doc in query.stream():
            cliente_data = doc.to_dict()
            
            # Verificar status
            status_por_negocio = cliente_data.get('status_por_negocio', {})
            user_status = status_por_negocio.get(negocio_id, 'ativo')
            
            if user_status == status:
                cliente_data['id'] = doc.id
                
                # Descriptografar campos sensíveis
                cliente_data = decrypt_user_sensitive_fields(cliente_data, USER_SENSITIVE_FIELDS)
                
                clientes.append(cliente_data)
        
        logger.info(f"Retornando {len(clientes)} clientes para o negócio {negocio_id} com status {status}")
        return clientes
    except Exception as e:
        logger.error(f"Erro ao listar clientes do negócio {negocio_id}: {e}")
        return []


def admin_promover_cliente_para_profissional(db: firestore.client, negocio_id: str, cliente_uid: str) -> Optional[Dict]:
    """Promove um usuário de 'cliente' para 'profissional' e cria seu perfil profissional."""
    from .usuarios import buscar_usuario_por_firebase_uid
    from .profissionais import criar_profissional
    
    try:
        user_doc = buscar_usuario_por_firebase_uid(db, cliente_uid)
        if not user_doc:
            logger.warning(f"Tentativa de promover usuário inexistente com UID: {cliente_uid}")
            return None

        if user_doc.get("roles", {}).get(negocio_id) == 'cliente':
            # 1. Atualiza a permissão do usuário
            user_ref = db.collection('usuarios').document(user_doc['id'])
            user_ref.update({
                f'roles.{negocio_id}': 'profissional'
            })
            
            # 2. Cria o perfil profissional básico
            novo_profissional_data = schemas.ProfissionalCreate(
                negocio_id=negocio_id,
                usuario_uid=cliente_uid,
                nome=user_doc.get('nome', 'Profissional sem nome'),
                especialidades="A definir",
                ativo=True,
                fotos={}
            )
            criar_profissional(db, novo_profissional_data)
            
            logger.info(f"Usuário {user_doc['email']} promovido para profissional no negócio {negocio_id}.")
            
            # Retorna os dados atualizados do usuário
            return buscar_usuario_por_firebase_uid(db, cliente_uid)
        else:
            logger.warning(f"Usuário {user_doc.get('email')} não é um cliente deste negócio e não pode ser promovido.")
            return None
    except Exception as e:
        logger.error(f"Erro ao promover cliente {cliente_uid} para profissional: {e}")
        return None


def admin_rebaixar_profissional_para_cliente(db: firestore.client, negocio_id: str, profissional_uid: str) -> Optional[Dict]:
    """Rebaixa um usuário de 'profissional' para 'cliente' e desativa seu perfil profissional."""
    from .usuarios import buscar_usuario_por_firebase_uid
    
    try:
        user_doc = buscar_usuario_por_firebase_uid(db, profissional_uid)
        if not user_doc:
            logger.warning(f"Tentativa de rebaixar usuário inexistente com UID: {profissional_uid}")
            return None

        if user_doc.get("roles", {}).get(negocio_id) == 'profissional':
            # 1. Atualiza a permissão do usuário
            user_ref = db.collection('usuarios').document(user_doc['id'])
            user_ref.update({
                f'roles.{negocio_id}': 'cliente'
            })
            
            # 2. Desativa o perfil profissional
            profissional_query = db.collection('profissionais') \
                .where('usuario_uid', '==', profissional_uid) \
                .where('negocio_id', '==', negocio_id)
            
            for doc in profissional_query.stream():
                doc.reference.update({'ativo': False})
            
            logger.info(f"Usuário {user_doc['email']} rebaixado para cliente no negócio {negocio_id}.")
            
            # Retorna os dados atualizados do usuário
            return buscar_usuario_por_firebase_uid(db, profissional_uid)
        else:
            logger.warning(f"Usuário {user_doc.get('email')} não é um profissional deste negócio e não pode ser rebaixado.")
            return None
    except Exception as e:
        logger.error(f"Erro ao rebaixar profissional {profissional_uid} para cliente: {e}")
        return None