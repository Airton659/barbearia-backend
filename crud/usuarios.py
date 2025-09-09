# crud/usuarios.py
"""
CRUD para gestão de usuários e autenticação
"""

import logging
from typing import Optional, Dict
from firebase_admin import firestore
import schemas
from crypto_utils import encrypt_data, decrypt_data
from .utils import (
    encrypt_user_sensitive_fields,
    decrypt_user_sensitive_fields,
    encrypt_endereco_fields,
    decrypt_endereco_fields,
)

logger = logging.getLogger(__name__)

USER_SENSITIVE_FIELDS = ['nome', 'telefone']

def buscar_usuario_por_firebase_uid(db: firestore.client, firebase_uid: str) -> Optional[Dict]:
    """Busca um usuário na coleção 'usuarios' pelo seu firebase_uid e descriptografa os dados sensíveis."""
    try:
        query = db.collection('usuarios').where('firebase_uid', '==', firebase_uid).limit(1)
        docs = list(query.stream())
        
        if docs:
            user_doc = docs[0].to_dict()
            user_doc['id'] = docs[0].id
            
            logger.info(f"Retornando usuário ID: {user_doc['id']} para firebase_uid: {firebase_uid}")
            
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
    Esta função é a fonte da verdade para a lógica de onboarding, como no backup.
    """
    negocio_id = user_data.negocio_id
    
    # Criptografa os dados antes de salvar
    dados_para_criptografar = {'nome': user_data.nome, 'telefone': user_data.telefone}
    dados_criptografados = encrypt_user_sensitive_fields(dados_para_criptografar, USER_SENSITIVE_FIELDS)
    
    # Fluxo de Super Admin (lógica do backup)
    if not negocio_id:
        if not db.collection('usuarios').limit(1).get():
            user_dict = {
                "nome": dados_criptografados['nome'], "email": user_data.email, "firebase_uid": user_data.firebase_uid,
                "roles": {"platform": "super_admin"}, "fcm_tokens": []
            }
            if dados_criptografados['telefone']:
                user_dict['telefone'] = dados_criptografados['telefone']
            
            doc_ref = db.collection('usuarios').document()
            doc_ref.set(user_dict)
            user_dict['id'] = doc_ref.id
            logger.info(f"Novo usuário {user_data.email} criado como Super Admin.")
            
            user_dict['nome'] = user_data.nome
            user_dict['telefone'] = user_data.telefone
            return user_dict
        else:
            raise ValueError("Não é possível se registrar sem um negócio específico.")
    
    # Fluxo multi-tenant (lógica do backup)
    @firestore.transactional
    def transaction_sync_user(transaction):
        user_existente = buscar_usuario_por_firebase_uid(db, user_data.firebase_uid)
        negocio_doc_ref = db.collection('negocios').document(negocio_id)
        negocio_doc = negocio_doc_ref.get(transaction=transaction)
        
        if not negocio_doc.exists:
            raise ValueError(f"O negócio com ID '{negocio_id}' não foi encontrado.")

        negocio_data = negocio_doc.to_dict()
        role = "cliente"
        has_admin = negocio_data.get('admin_uid') is not None
        
        if not has_admin and user_data.codigo_convite and user_data.codigo_convite == negocio_data.get('codigo_convite'):
            role = "admin"
        
        if user_existente:
            user_ref = db.collection('usuarios').document(user_existente['id'])
            # Atualiza os dados principais se estiverem sendo enviados (lógica de update)
            update_fields = {}
            if user_data.nome:
                update_fields['nome'] = dados_criptografados['nome']
            if user_data.telefone:
                update_fields['telefone'] = dados_criptografados['telefone']
            
            if update_fields:
                 transaction.update(user_ref, update_fields)

            if negocio_id not in user_existente.get("roles", {}):
                transaction.update(user_ref, {f'roles.{negocio_id}': role})
                if role == "admin":
                    transaction.update(negocio_doc_ref, {'admin_uid': user_data.firebase_uid})
            
            # Retorna os dados atualizados (já descriptografados pela busca)
            return buscar_usuario_por_firebase_uid(db, user_data.firebase_uid)
        
        # Criar novo usuário
        user_dict = {
            "nome": dados_criptografados['nome'], "email": user_data.email, "firebase_uid": user_data.firebase_uid,
            "roles": {negocio_id: role}, "fcm_tokens": []
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
        return user_dict
    
    return transaction_sync_user(db.transaction())

def adicionar_fcm_token(db: firestore.client, firebase_uid: str, fcm_token: str):
    """Adiciona um FCM token a um usuário, evitando duplicatas."""
    user_doc = buscar_usuario_por_firebase_uid(db, firebase_uid)
    if user_doc:
        doc_ref = db.collection('usuarios').document(user_doc['id'])
        doc_ref.update({'fcm_tokens': firestore.ArrayUnion([fcm_token])})

def remover_fcm_token(db: firestore.client, firebase_uid: str, fcm_token: str):
    """Remove um FCM token de um usuário."""
    user_doc = buscar_usuario_por_firebase_uid(db, firebase_uid)
    if user_doc:
        doc_ref = db.collection('usuarios').document(user_doc['id'])
        doc_ref.update({'fcm_tokens': firestore.ArrayRemove([fcm_token])})