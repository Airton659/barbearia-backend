# crud/negocios.py
"""
CRUD para gestão de negócios
"""

import logging
from typing import List, Dict
from firebase_admin import firestore
import schemas
from .utils import add_timestamps

logger = logging.getLogger(__name__)


def admin_criar_negocio(db: firestore.client, negocio_data: schemas.NegocioCreate, owner_uid: str) -> Dict:
    """Cria um novo negócio (apenas para Super Admins)."""
    try:
        # Preparar dados do negócio
        negocio_dict = negocio_data.model_dump()
        negocio_dict['owner_uid'] = owner_uid
        negocio_dict['admin_uid'] = None  # Será preenchido quando um admin se registrar
        
        # Adicionar timestamps
        negocio_dict = add_timestamps(negocio_dict, is_update=False)
        
        # Salvar no Firestore
        doc_ref = db.collection('negocios').document()
        doc_ref.set(negocio_dict)
        negocio_dict['id'] = doc_ref.id
        
        logger.info(f"Negócio {negocio_data.nome} criado pelo Super Admin {owner_uid}")
        return negocio_dict
        
    except Exception as e:
        logger.error(f"Erro ao criar negócio: {e}")
        raise


def admin_listar_negocios(db: firestore.client) -> List[Dict]:
    """Lista todos os negócios (apenas para Super Admins)."""
    negocios = []
    try:
        query = db.collection('negocios').order_by('created_at', direction=firestore.Query.DESCENDING)
        
        for doc in query.stream():
            negocio_data = doc.to_dict()
            negocio_data['id'] = doc.id
            negocios.append(negocio_data)
        
        logger.info(f"Retornando {len(negocios)} negócios")
        return negocios
    except Exception as e:
        logger.error(f"Erro ao listar negócios: {e}")
        return []


def buscar_negocio_por_id(db: firestore.client, negocio_id: str) -> Dict:
    """Busca um negócio pelo ID."""
    try:
        doc = db.collection('negocios').document(negocio_id).get()
        if doc.exists:
            negocio_data = doc.to_dict()
            negocio_data['id'] = doc.id
            return negocio_data
        return None
    except Exception as e:
        logger.error(f"Erro ao buscar negócio {negocio_id}: {e}")
        return None


def atualizar_negocio(db: firestore.client, negocio_id: str, update_data: schemas.NegocioUpdate) -> Dict:
    """Atualiza dados de um negócio."""
    try:
        negocio_ref = db.collection('negocios').document(negocio_id)
        negocio_doc = negocio_ref.get()
        
        if not negocio_doc.exists:
            logger.warning(f"Negócio {negocio_id} não encontrado")
            return None
        
        # Preparar dados para atualização
        update_dict = update_data.model_dump(exclude_unset=True)
        update_dict['updated_at'] = firestore.SERVER_TIMESTAMP
        
        # Atualizar
        negocio_ref.update(update_dict)
        
        # Retornar dados atualizados
        updated_doc = negocio_ref.get()
        updated_data = updated_doc.to_dict()
        updated_data['id'] = updated_doc.id
        
        logger.info(f"Negócio {negocio_id} atualizado com sucesso")
        return updated_data
        
    except Exception as e:
        logger.error(f"Erro ao atualizar negócio {negocio_id}: {e}")
        return None