# crud/usuarios.py
"""
CRUD para gestão de usuários e autenticação
"""

import logging
from typing import Optional, Dict
from firebase_admin import firestore
import schemas
from crypto_utils import encrypt_data, decrypt_data
from crud.utils import (
    encrypt_user_sensitive_fields,
    decrypt_user_sensitive_fields,
    encrypt_endereco_fields,
    decrypt_endereco_fields,
    validate_phone_number,
    validate_cep,
    processar_imagem_base64
)

logger = logging.getLogger(__name__)

# Campos sensíveis que precisam de criptografia
USER_SENSITIVE_FIELDS = ['nome', 'telefone']


def buscar_usuario_por_firebase_uid(db: firestore.client, firebase_uid: str) -> Optional[Dict]:
    """Busca um usuário na coleção 'usuarios' pelo seu firebase_uid e descriptografa os dados sensíveis."""
    try:
        query = db.collection('usuarios').where('firebase_uid', '==', firebase_uid).order_by('created_at')
        docs = list(query.stream())
        
        # LOG CRÍTICO: Verificar se há usuários duplicados
        if len(docs) > 1:
            logger.critical(f"🚨 USUÁRIOS DUPLICADOS ENCONTRADOS para firebase_uid {firebase_uid}:")
            for i, doc in enumerate(docs):
                doc_data = doc.to_dict()
                logger.critical(f"  {i+1}. ID: {doc.id}, roles: {doc_data.get('roles', {})}, created_at: {doc_data.get('created_at')}")
        
        if docs:
            # SEMPRE pegar o PRIMEIRO usuário (mais antigo) para garantir consistência
            user_doc = docs[0].to_dict()
            user_doc['id'] = docs[0].id
            
            logger.info(f"Retornando usuário ID: {user_doc['id']} para firebase_uid: {firebase_uid}")
            
            # Descriptografa os campos sensíveis
            user_doc = decrypt_user_sensitive_fields(user_doc, USER_SENSITIVE_FIELDS)
            
            if 'endereco' in user_doc and user_doc['endereco']:
                user_doc['endereco'] = decrypt_endereco_fields(user_doc['endereco'])
            
            return user_doc
        return None
    except Exception as e:
        logger.error(f"Erro ao buscar/descriptografar usuário por firebase_uid {firebase_uid}: {e}")
        return None


def criar_ou_atualizar_usuario(db: firestore.client, user_data: schemas.UsuarioSync) -> Dict:
    """
    Cria ou atualiza um usuário no Firestore, criptografando dados sensíveis.
    Esta função é a única fonte da verdade para a lógica de onboarding.
    """
    negocio_id = user_data.negocio_id
    
    # Criptografa os dados antes de salvar
    dados_para_criptografar = {
        'nome': user_data.nome,
        'telefone': user_data.telefone
    }
    dados_criptografados = encrypt_user_sensitive_fields(dados_para_criptografar, USER_SENSITIVE_FIELDS)
    
    # Fluxo de Super Admin (sem negocio_id)
    is_super_admin_flow = not negocio_id
    if is_super_admin_flow:
        if not db.collection('usuarios').limit(1).get():
            user_dict = {
                "nome": dados_criptografados['nome'], 
                "email": user_data.email, 
                "firebase_uid": user_data.firebase_uid,
                "roles": {"platform": "super_admin"}, 
                "fcm_tokens": []
            }
            if dados_criptografados['telefone']:
                user_dict['telefone'] = dados_criptografados['telefone']
            
            doc_ref = db.collection('usuarios').document()
            doc_ref.set(user_dict)
            user_dict['id'] = doc_ref.id
            logger.info(f"Novo usuário {user_data.email} criado como Super Admin.")
            
            # Descriptografa para retornar ao usuário
            user_dict['nome'] = user_data.nome
            user_dict['telefone'] = user_data.telefone
            return user_dict
        else:
            raise ValueError("Não é possível se registrar sem um negócio específico.")
    
    # Fluxo multi-tenant
    @firestore.transactional
    def transaction_sync_user(transaction):
        logger.critical(f"🔄 TRANSAÇÃO SYNC - Buscando firebase_uid: {user_data.firebase_uid}")
        user_existente = buscar_usuario_por_firebase_uid(db, user_data.firebase_uid)
        
        # PROTEÇÃO CRÍTICA: Verificar duplicatas antes de criar
        if not user_existente:
            # Verificar SE REALMENTE não existe (proteção adicional)
            query_check = db.collection('usuarios').where('firebase_uid', '==', user_data.firebase_uid)
            existing_docs = list(query_check.stream())
            if existing_docs:
                logger.critical(f"🚨 USUÁRIO EXISTE MAS buscar_usuario_por_firebase_uid retornou None!")
                logger.critical(f"🚨 Docs encontrados: {[doc.id for doc in existing_docs]}")
                # Usar o primeiro usuário encontrado
                first_doc = existing_docs[0]
                user_data_dict = first_doc.to_dict()
                user_data_dict['id'] = first_doc.id
                user_existente = decrypt_user_sensitive_fields(user_data_dict, USER_SENSITIVE_FIELDS)
        
        logger.critical(f"🔄 USER_EXISTENTE: {'SIM' if user_existente else 'NÃO'}, ID: {user_existente.get('id') if user_existente else 'N/A'}")
        
        negocio_doc_ref = db.collection('negocios').document(negocio_id)
        negocio_doc = negocio_doc_ref.get(transaction=transaction)
        negocio_data = negocio_doc.to_dict()
        
        role = "cliente"
        has_admin = negocio_data.get('admin_uid') is not None
        
        if not has_admin and user_data.codigo_convite and user_data.codigo_convite == negocio_data.get('codigo_convite'):
            role = "admin"
        
        if user_existente:
            user_ref = db.collection('usuarios').document(user_existente['id'])
            if negocio_id not in user_existente.get("roles", {}):
                transaction.update(user_ref, {f'roles.{negocio_id}': role})
                user_existente["roles"][negocio_id] = role
                if role == "admin":
                    transaction.update(negocio_doc_ref, {'admin_uid': user_data.firebase_uid})
            return user_existente
        
        # Criar novo usuário
        logger.critical(f"🆕 CRIANDO NOVO USUÁRIO - firebase_uid: {user_data.firebase_uid}, email: {user_data.email}, role: {role}")
        user_dict = {
            "nome": dados_criptografados['nome'], 
            "email": user_data.email, 
            "firebase_uid": user_data.firebase_uid,
            "roles": {negocio_id: role}, 
            "fcm_tokens": []
        }
        if dados_criptografados['telefone']:
            user_dict['telefone'] = dados_criptografados['telefone']
        
        new_user_ref = db.collection('usuarios').document()
        transaction.set(new_user_ref, user_dict)
        user_dict['id'] = new_user_ref.id
        
        if role == "admin":
            transaction.update(negocio_doc_ref, {'admin_uid': user_data.firebase_uid})
        
        # Descriptografa para retornar ao usuário
        user_dict['nome'] = user_data.nome
        user_dict['telefone'] = user_data.telefone
        if 'endereco' in user_dict and user_dict['endereco']:
             user_dict['endereco'] = user_data.endereco.dict()
        return user_dict
    
    return transaction_sync_user(db.transaction())


def adicionar_fcm_token(db: firestore.client, firebase_uid: str, fcm_token: str):
    """Adiciona um FCM token a um usuário, evitando duplicatas."""
    try:
        user_doc = buscar_usuario_por_firebase_uid(db, firebase_uid)
        if user_doc:
            doc_ref = db.collection('usuarios').document(user_doc['id'])
            doc_ref.update({
                'fcm_tokens': firestore.ArrayUnion([fcm_token])
            })
    except Exception as e:
        logger.error(f"Erro ao adicionar FCM token para o UID {firebase_uid}: {e}")


def remover_fcm_token(db: firestore.client, firebase_uid: str, fcm_token: str):
    """Remove um FCM token de um usuário."""
    try:
        user_doc = buscar_usuario_por_firebase_uid(db, firebase_uid)
        if user_doc:
            doc_ref = db.collection('usuarios').document(user_doc['id'])
            doc_ref.update({
                'fcm_tokens': firestore.ArrayRemove([fcm_token])
            })
    except Exception as e:
        logger.error(f"Erro ao remover FCM token para o UID {firebase_uid}: {e}")


def atualizar_perfil_usuario(db: firestore.client, user_id: str, negocio_id: str, update_data: schemas.UserProfileUpdate, profile_image_url: Optional[str] = None) -> Optional[Dict]:
    """
    Atualiza o perfil do usuário com validações de segurança.
    """
    try:
        logger.critical(f"🔧 ATUALIZAR-PERFIL - user_id: {user_id}, negocio_id: {negocio_id}")
        
        # Buscar usuário no Firestore
        user_ref = db.collection('usuarios').document(user_id)
        user_doc = user_ref.get()
        
        logger.critical(f"🔧 DOCUMENTO ENCONTRADO: exists={user_doc.exists}, id={user_doc.id if user_doc.exists else 'N/A'}")
        
        if not user_doc.exists:
            logger.warning(f"Usuário {user_id} não encontrado")
            return None
            
        user_data = user_doc.to_dict()
        
        # Verificar se usuário pertence ao negócio
        user_roles = user_data.get('roles', {})
        if negocio_id not in user_roles:
            logger.warning(f"Usuário {user_id} não pertence ao negócio {negocio_id}")
            return None
        
        # Preparar dados para atualização
        update_dict = {}
        
        # Nome (obrigatório e sempre criptografado)
        if update_data.nome:
            update_dict['nome'] = encrypt_data(update_data.nome.strip())
        
        # Telefone (opcional, criptografado se fornecido)
        if update_data.telefone is not None:
            if update_data.telefone.strip():
                if not validate_phone_number(update_data.telefone):
                    raise ValueError("Telefone deve conter pelo menos 10 dígitos (DDD + número)")
                update_dict['telefone'] = encrypt_data(update_data.telefone.strip())
            else:
                update_dict['telefone'] = None
        
        # Endereço (opcional, criptografado se fornecido)
        if update_data.endereco is not None:
            endereco_dict = update_data.endereco.model_dump()
            # Validar CEP se fornecido
            if endereco_dict.get('cep') and not validate_cep(endereco_dict['cep']):
                raise ValueError("CEP deve conter exatamente 8 dígitos")
            update_dict['endereco'] = encrypt_endereco_fields(endereco_dict)
        
        # URL da imagem de perfil (se fornecida)
        if profile_image_url is not None:
            update_dict['profile_image_url'] = profile_image_url
        
        # Adicionar timestamp de atualização
        update_dict['updated_at'] = firestore.SERVER_TIMESTAMP
        
        # Executar atualização
        user_ref.update(update_dict)
        logger.critical(f"✅ PERFIL ATUALIZADO COM SUCESSO - user_id: {user_id}")
        
        # Buscar dados atualizados e descriptografar para resposta
        updated_doc = user_ref.get()
        updated_data = updated_doc.to_dict()
        updated_data['id'] = updated_doc.id
        
        logger.critical(f"✅ DADOS ATUALIZADOS RETORNADOS - user_id: {updated_data['id']}, roles: {updated_data.get('roles', {})}")
        
        # Descriptografar dados para resposta
        updated_data = decrypt_user_sensitive_fields(updated_data, USER_SENSITIVE_FIELDS)
        
        if 'endereco' in updated_data and updated_data['endereco']:
            updated_data['endereco'] = decrypt_endereco_fields(updated_data['endereco'])
        
        return updated_data
        
    except ValueError as ve:
        logger.warning(f"Erro de validação ao atualizar perfil do usuário {user_id}: {ve}")
        raise
    except Exception as e:
        logger.error(f"Erro ao atualizar perfil do usuário {user_id}: {e}")
        return None