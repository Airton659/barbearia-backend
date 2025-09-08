# crud/profissionais.py
"""
CRUD para gestão de profissionais e serviços
"""

import logging
from typing import Optional, List, Dict
from firebase_admin import firestore
import schemas
from .utils import decrypt_user_sensitive_fields, add_timestamps

logger = logging.getLogger(__name__)

# Campos sensíveis que precisam de criptografia
USER_SENSITIVE_FIELDS = ['nome', 'telefone']


def buscar_profissional_por_uid(db: firestore.client, negocio_id: str, firebase_uid: str) -> Optional[Dict]:
    """Busca um profissional pelo firebase_uid em um negócio específico."""
    try:
        # Primeiro buscar o usuário
        user_query = db.collection('usuarios').where('firebase_uid', '==', firebase_uid).limit(1)
        user_docs = list(user_query.stream())
        
        if not user_docs:
            return None
            
        user_data = user_docs[0].to_dict()
        user_data['id'] = user_docs[0].id
        
        # Verificar se é profissional neste negócio
        roles = user_data.get('roles', {})
        if roles.get(negocio_id) not in ['profissional', 'admin']:
            return None
        
        # Buscar perfil profissional
        prof_query = db.collection('profissionais') \
                      .where('negocio_id', '==', negocio_id) \
                      .where('usuario_uid', '==', firebase_uid) \
                      .limit(1)
        
        prof_docs = list(prof_query.stream())
        if prof_docs:
            prof_data = prof_docs[0].to_dict()
            prof_data['id'] = prof_docs[0].id
            
            # Descriptografar dados do usuário
            user_data = decrypt_user_sensitive_fields(user_data, USER_SENSITIVE_FIELDS)
            
            # Combinar dados
            prof_data.update({
                'nome': user_data.get('nome'),
                'email': user_data.get('email'),
                'telefone': user_data.get('telefone')
            })
            
            return prof_data
            
        return None
    except Exception as e:
        logger.error(f"Erro ao buscar profissional por UID {firebase_uid}: {e}")
        return None


def criar_profissional(db: firestore.client, profissional_data: schemas.ProfissionalCreate) -> Dict:
    """Cria um novo perfil profissional."""
    try:
        # Preparar dados
        prof_dict = profissional_data.model_dump()
        prof_dict = add_timestamps(prof_dict, is_update=False)
        
        # Salvar no Firestore
        doc_ref = db.collection('profissionais').document()
        doc_ref.set(prof_dict)
        prof_dict['id'] = doc_ref.id
        
        logger.info(f"Profissional criado para usuário {profissional_data.usuario_uid}")
        return prof_dict
        
    except Exception as e:
        logger.error(f"Erro ao criar profissional: {e}")
        raise


def listar_profissionais_por_negocio(db: firestore.client, negocio_id: str) -> List[Dict]:
    """Lista todos os profissionais ativos de um negócio."""
    profissionais = []
    try:
        query = db.collection('profissionais') \
                 .where('negocio_id', '==', negocio_id) \
                 .where('ativo', '==', True)
        
        for doc in query.stream():
            prof_data = doc.to_dict()
            prof_data['id'] = doc.id
            
            # Buscar dados do usuário
            usuario_uid = prof_data.get('usuario_uid')
            if usuario_uid:
                user_query = db.collection('usuarios').where('firebase_uid', '==', usuario_uid).limit(1)
                user_docs = list(user_query.stream())
                
                if user_docs:
                    user_data = user_docs[0].to_dict()
                    user_data = decrypt_user_sensitive_fields(user_data, USER_SENSITIVE_FIELDS)
                    
                    prof_data.update({
                        'nome': user_data.get('nome'),
                        'email': user_data.get('email'),
                        'telefone': user_data.get('telefone')
                    })
            
            profissionais.append(prof_data)
        
        logger.info(f"Retornando {len(profissionais)} profissionais para o negócio {negocio_id}")
        return profissionais
    except Exception as e:
        logger.error(f"Erro ao listar profissionais do negócio {negocio_id}: {e}")
        return []


def buscar_profissional_por_id(db: firestore.client, profissional_id: str) -> Optional[Dict]:
    """Busca um profissional pelo ID."""
    try:
        doc = db.collection('profissionais').document(profissional_id).get()
        if doc.exists:
            prof_data = doc.to_dict()
            prof_data['id'] = doc.id
            
            # Buscar dados do usuário
            usuario_uid = prof_data.get('usuario_uid')
            if usuario_uid:
                user_query = db.collection('usuarios').where('firebase_uid', '==', usuario_uid).limit(1)
                user_docs = list(user_query.stream())
                
                if user_docs:
                    user_data = user_docs[0].to_dict()
                    user_data = decrypt_user_sensitive_fields(user_data, USER_SENSITIVE_FIELDS)
                    
                    prof_data.update({
                        'nome': user_data.get('nome'),
                        'email': user_data.get('email'),
                        'telefone': user_data.get('telefone')
                    })
            
            return prof_data
        return None
    except Exception as e:
        logger.error(f"Erro ao buscar profissional {profissional_id}: {e}")
        return None


def atualizar_perfil_profissional(db: firestore.client, profissional_id: str, update_data: schemas.ProfissionalUpdate) -> Optional[Dict]:
    """Atualiza o perfil de um profissional."""
    try:
        prof_ref = db.collection('profissionais').document(profissional_id)
        prof_doc = prof_ref.get()
        
        if not prof_doc.exists:
            logger.warning(f"Profissional {profissional_id} não encontrado")
            return None
        
        # Preparar dados para atualização
        update_dict = update_data.model_dump(exclude_unset=True)
        update_dict['updated_at'] = firestore.SERVER_TIMESTAMP
        
        # Atualizar
        prof_ref.update(update_dict)
        
        # Retornar dados atualizados
        return buscar_profissional_por_id(db, profissional_id)
        
    except Exception as e:
        logger.error(f"Erro ao atualizar profissional {profissional_id}: {e}")
        return None


# ===== SERVIÇOS =====

def criar_servico(db: firestore.client, servico_data: schemas.ServicoCreate) -> Dict:
    """Cria um novo serviço para um profissional."""
    try:
        # Preparar dados
        servico_dict = servico_data.model_dump()
        servico_dict = add_timestamps(servico_dict, is_update=False)
        
        # Salvar no Firestore
        doc_ref = db.collection('servicos').document()
        doc_ref.set(servico_dict)
        servico_dict['id'] = doc_ref.id
        
        logger.info(f"Serviço {servico_data.nome} criado para profissional {servico_data.profissional_id}")
        return servico_dict
        
    except Exception as e:
        logger.error(f"Erro ao criar serviço: {e}")
        raise


def listar_servicos_por_profissional(db: firestore.client, profissional_id: str) -> List[Dict]:
    """Lista todos os serviços de um profissional."""
    servicos = []
    try:
        query = db.collection('servicos') \
                 .where('profissional_id', '==', profissional_id) \
                 .where('ativo', '==', True)
        
        for doc in query.stream():
            servico_data = doc.to_dict()
            servico_data['id'] = doc.id
            servicos.append(servico_data)
        
        logger.info(f"Retornando {len(servicos)} serviços para o profissional {profissional_id}")
        return servicos
    except Exception as e:
        logger.error(f"Erro ao listar serviços do profissional {profissional_id}: {e}")
        return []


def atualizar_servico(db: firestore.client, servico_id: str, profissional_id: str, update_data: schemas.ServicoUpdate) -> Optional[Dict]:
    """Atualiza um serviço específico."""
    try:
        servico_ref = db.collection('servicos').document(servico_id)
        servico_doc = servico_ref.get()
        
        if not servico_doc.exists:
            logger.warning(f"Serviço {servico_id} não encontrado")
            return None
        
        servico_data = servico_doc.to_dict()
        
        # Verificar se o serviço pertence ao profissional
        if servico_data.get('profissional_id') != profissional_id:
            logger.warning(f"Serviço {servico_id} não pertence ao profissional {profissional_id}")
            return None
        
        # Preparar dados para atualização
        update_dict = update_data.model_dump(exclude_unset=True)
        update_dict['updated_at'] = firestore.SERVER_TIMESTAMP
        
        # Atualizar
        servico_ref.update(update_dict)
        
        # Retornar dados atualizados
        updated_doc = servico_ref.get()
        updated_data = updated_doc.to_dict()
        updated_data['id'] = updated_doc.id
        
        logger.info(f"Serviço {servico_id} atualizado com sucesso")
        return updated_data
        
    except Exception as e:
        logger.error(f"Erro ao atualizar serviço {servico_id}: {e}")
        return None


def deletar_servico(db: firestore.client, servico_id: str, profissional_id: str) -> bool:
    """Marca um serviço como inativo (soft delete)."""
    try:
        servico_ref = db.collection('servicos').document(servico_id)
        servico_doc = servico_ref.get()
        
        if not servico_doc.exists:
            logger.warning(f"Serviço {servico_id} não encontrado")
            return False
        
        servico_data = servico_doc.to_dict()
        
        # Verificar se o serviço pertence ao profissional
        if servico_data.get('profissional_id') != profissional_id:
            logger.warning(f"Serviço {servico_id} não pertence ao profissional {profissional_id}")
            return False
        
        # Marcar como inativo
        servico_ref.update({
            'ativo': False,
            'updated_at': firestore.SERVER_TIMESTAMP
        })
        
        logger.info(f"Serviço {servico_id} deletado (inativado) com sucesso")
        return True
        
    except Exception as e:
        logger.error(f"Erro ao deletar serviço {servico_id}: {e}")
        return False