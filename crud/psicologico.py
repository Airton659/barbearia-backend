# crud/psicologico.py
"""
CRUD para gestão de suporte psicológico
"""

import logging
from typing import Optional, List, Dict
from firebase_admin import firestore
import schemas
from crud.utils import add_timestamps

logger = logging.getLogger(__name__)


def criar_suporte_psicologico(db: firestore.client, suporte_data: schemas.SuportePsicologicoCreate, psicologo_id: str) -> Dict:
    """Cria um novo registro de suporte psicológico."""
    try:
        suporte_dict = suporte_data.model_dump()
        suporte_dict['psicologo_id'] = psicologo_id
        suporte_dict['status'] = 'ativo'
        suporte_dict = add_timestamps(suporte_dict, is_update=False)
        
        doc_ref = db.collection('suporte_psicologico').document()
        doc_ref.set(suporte_dict)
        suporte_dict['id'] = doc_ref.id
        
        logger.info(f"Suporte psicológico criado para paciente {suporte_data.paciente_id}")
        return suporte_dict
        
    except Exception as e:
        logger.error(f"Erro ao criar suporte psicológico: {e}")
        raise


def listar_suportes_psicologicos(db: firestore.client, paciente_id: str) -> List[Dict]:
    """Lista todos os suportes psicológicos de um paciente."""
    suportes = []
    try:
        query = db.collection('suporte_psicologico') \
                 .where('paciente_id', '==', paciente_id) \
                 .order_by('created_at', direction=firestore.Query.DESCENDING)
        
        for doc in query.stream():
            suporte_data = doc.to_dict()
            suporte_data['id'] = doc.id
            suportes.append(suporte_data)
        
        logger.info(f"Retornando {len(suportes)} suportes psicológicos para paciente {paciente_id}")
        return suportes
        
    except Exception as e:
        logger.error(f"Erro ao listar suportes psicológicos: {e}")
        return []


def atualizar_suporte_psicologico(db: firestore.client, suporte_id: str, update_data: schemas.SuportePsicologicoUpdate, psicologo_id: str) -> Optional[Dict]:
    """Atualiza um registro de suporte psicológico."""
    try:
        suporte_ref = db.collection('suporte_psicologico').document(suporte_id)
        suporte_doc = suporte_ref.get()
        
        if not suporte_doc.exists:
            return None
        
        suporte_data = suporte_doc.to_dict()
        
        # Verificar se o psicólogo pode editar
        if suporte_data.get('psicologo_id') != psicologo_id:
            return None
        
        update_dict = update_data.model_dump(exclude_unset=True)
        update_dict['updated_at'] = firestore.SERVER_TIMESTAMP
        
        suporte_ref.update(update_dict)
        
        updated_doc = suporte_ref.get()
        updated_data = updated_doc.to_dict()
        updated_data['id'] = updated_doc.id
        
        logger.info(f"Suporte psicológico {suporte_id} atualizado")
        return updated_data
        
    except Exception as e:
        logger.error(f"Erro ao atualizar suporte psicológico: {e}")
        return None


def deletar_suporte_psicologico(db: firestore.client, suporte_id: str, psicologo_id: str) -> bool:
    """Remove um registro de suporte psicológico."""
    try:
        suporte_ref = db.collection('suporte_psicologico').document(suporte_id)
        suporte_doc = suporte_ref.get()
        
        if not suporte_doc.exists:
            return False
        
        suporte_data = suporte_doc.to_dict()
        
        # Verificar se o psicólogo pode deletar
        if suporte_data.get('psicologo_id') != psicologo_id:
            return False
        
        suporte_ref.delete()
        logger.info(f"Suporte psicológico {suporte_id} removido")
        return True
        
    except Exception as e:
        logger.error(f"Erro ao deletar suporte psicológico: {e}")
        return False


def listar_tecnicos_supervisionados_por_paciente(db: firestore.client, paciente_id: str) -> List[Dict]:
    """Lista os técnicos que supervisionam um paciente específico."""
    tecnicos = []
    try:
        # Buscar vínculos do paciente
        paciente_ref = db.collection('usuarios').document(paciente_id)
        paciente_doc = paciente_ref.get()
        
        if not paciente_doc.exists:
            return []
        
        paciente_data = paciente_doc.to_dict()
        tecnicos_vinculados = paciente_data.get('tecnicos_vinculados', [])
        
        # Buscar dados dos técnicos
        for tecnico_id in tecnicos_vinculados:
            tecnico_doc = db.collection('usuarios').document(tecnico_id).get()
            if tecnico_doc.exists:
                tecnico_data = tecnico_doc.to_dict()
                tecnico_data['id'] = tecnico_doc.id
                
                # Descriptografar dados sensíveis se necessário
                from crud.utils import decrypt_user_sensitive_fields
                tecnico_data = decrypt_user_sensitive_fields(tecnico_data, ['nome', 'telefone'])
                
                tecnicos.append(tecnico_data)
        
        logger.info(f"Retornando {len(tecnicos)} técnicos supervisionando paciente {paciente_id}")
        return tecnicos
        
    except Exception as e:
        logger.error(f"Erro ao listar técnicos supervisionados: {e}")
        return []