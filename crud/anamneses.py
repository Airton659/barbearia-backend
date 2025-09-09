# crud/anamneses.py
"""
CRUD para gestão de anamneses
"""

import logging
from typing import Optional, List, Dict
from firebase_admin import firestore
import schemas
from crud.utils import add_timestamps

logger = logging.getLogger(__name__)


def criar_anamnese(db: firestore.client, paciente_id: str, anamnese_data: schemas.AnamneseCreate) -> Dict:
    """Cria uma nova anamnese para um paciente."""
    try:
        # Preparar dados da anamnese
        anamnese_dict = anamnese_data.model_dump()
        anamnese_dict['paciente_id'] = paciente_id
        
        # Adicionar timestamps
        anamnese_dict = add_timestamps(anamnese_dict, is_update=False)
        
        # Salvar no Firestore
        doc_ref = db.collection('anamneses').document()
        doc_ref.set(anamnese_dict)
        anamnese_dict['id'] = doc_ref.id
        
        logger.info(f"Anamnese criada para paciente {paciente_id}")
        return anamnese_dict
        
    except Exception as e:
        logger.error(f"Erro ao criar anamnese: {e}")
        raise


def listar_anamneses_por_paciente(db: firestore.client, paciente_id: str) -> List[Dict]:
    """Lista todas as anamneses de um paciente."""
    anamneses = []
    try:
        query = db.collection('anamneses') \
                 .where('paciente_id', '==', paciente_id) \
                 .order_by('created_at', direction=firestore.Query.DESCENDING)
        
        for doc in query.stream():
            anamnese_data = doc.to_dict()
            anamnese_data['id'] = doc.id
            anamneses.append(anamnese_data)
        
        logger.info(f"Retornando {len(anamneses)} anamneses para o paciente {paciente_id}")
        return anamneses
    except Exception as e:
        logger.error(f"Erro ao listar anamneses do paciente {paciente_id}: {e}")
        return []


def atualizar_anamnese(db: firestore.client, anamnese_id: str, paciente_id: str, update_data: schemas.AnamneseUpdate) -> Optional[Dict]:
    """Atualiza uma anamnese específica."""
    try:
        anamnese_ref = db.collection('anamneses').document(anamnese_id)
        anamnese_doc = anamnese_ref.get()
        
        if not anamnese_doc.exists:
            logger.warning(f"Anamnese {anamnese_id} não encontrada")
            return None
        
        anamnese_data = anamnese_doc.to_dict()
        
        # Verificar se a anamnese pertence ao paciente
        if anamnese_data.get('paciente_id') != paciente_id:
            logger.warning(f"Anamnese {anamnese_id} não pertence ao paciente {paciente_id}")
            return None
        
        # Preparar dados para atualização
        update_dict = update_data.model_dump(exclude_unset=True)
        update_dict['updated_at'] = firestore.SERVER_TIMESTAMP
        
        # Atualizar
        anamnese_ref.update(update_dict)
        
        # Retornar dados atualizados
        updated_doc = anamnese_ref.get()
        updated_data = updated_doc.to_dict()
        updated_data['id'] = updated_doc.id
        
        logger.info(f"Anamnese {anamnese_id} atualizada com sucesso")
        return updated_data
        
    except Exception as e:
        logger.error(f"Erro ao atualizar anamnese {anamnese_id}: {e}")
        return None


def criar_consulta(db: firestore.client, consulta_data: schemas.ConsultaCreate) -> Dict:
    """Cria uma nova consulta."""
    try:
        # Preparar dados da consulta
        consulta_dict = consulta_data.model_dump()
        
        # Adicionar timestamps
        consulta_dict = add_timestamps(consulta_dict, is_update=False)
        
        # Salvar no Firestore
        doc_ref = db.collection('consultas').document()
        doc_ref.set(consulta_dict)
        consulta_dict['id'] = doc_ref.id
        
        logger.info(f"Consulta criada para paciente {consulta_data.paciente_id}")
        return consulta_dict
        
    except Exception as e:
        logger.error(f"Erro ao criar consulta: {e}")
        raise


def criar_orientacao(db: firestore.client, orientacao_data: schemas.OrientacaoCreate, consulta_id: str) -> Dict:
    """Cria uma nova orientação dentro de uma consulta."""
    try:
        # Preparar dados da orientação
        orientacao_dict = orientacao_data.model_dump()
        orientacao_dict['consulta_id'] = consulta_id
        
        # Adicionar timestamps
        orientacao_dict = add_timestamps(orientacao_dict, is_update=False)
        
        # Salvar no Firestore
        doc_ref = db.collection('orientacoes').document()
        doc_ref.set(orientacao_dict)
        orientacao_dict['id'] = doc_ref.id
        
        logger.info(f"Orientação criada para consulta {consulta_id}")
        return orientacao_dict
        
    except Exception as e:
        logger.error(f"Erro ao criar orientação: {e}")
        raise


def listar_consultas(db: firestore.client, paciente_id: str) -> List[Dict]:
    """Lista todas as consultas de um paciente."""
    consultas = []
    try:
        query = db.collection('consultas') \
                 .where('paciente_id', '==', paciente_id) \
                 .order_by('created_at', direction=firestore.Query.DESCENDING)
        
        for doc in query.stream():
            consulta_data = doc.to_dict()
            consulta_data['id'] = doc.id
            consultas.append(consulta_data)
        
        logger.info(f"Retornando {len(consultas)} consultas para o paciente {paciente_id}")
        return consultas
    except Exception as e:
        logger.error(f"Erro ao listar consultas do paciente {paciente_id}: {e}")
        return []


def listar_orientacoes(db: firestore.client, paciente_id: str, consulta_id: str) -> List[Dict]:
    """Lista todas as orientações de uma consulta específica."""
    orientacoes = []
    try:
        query = db.collection('orientacoes') \
                 .where('consulta_id', '==', consulta_id) \
                 .order_by('created_at', direction=firestore.Query.DESCENDING)
        
        for doc in query.stream():
            orientacao_data = doc.to_dict()
            orientacao_data['id'] = doc.id
            orientacoes.append(orientacao_data)
        
        logger.info(f"Retornando {len(orientacoes)} orientações para a consulta {consulta_id}")
        return orientacoes
    except Exception as e:
        logger.error(f"Erro ao listar orientações da consulta {consulta_id}: {e}")
        return []


def listar_exames(db: firestore.client, paciente_id: str) -> List[Dict]:
    """Lista todos os exames de um paciente."""
    exames = []
    try:
        query = db.collection('exames') \
                 .where('paciente_id', '==', paciente_id) \
                 .order_by('created_at', direction=firestore.Query.DESCENDING)
        
        for doc in query.stream():
            exame_data = doc.to_dict()
            exame_data['id'] = doc.id
            exames.append(exame_data)
        
        logger.info(f"Retornando {len(exames)} exames para o paciente {paciente_id}")
        return exames
    except Exception as e:
        logger.error(f"Erro ao listar exames do paciente {paciente_id}: {e}")
        return []


def listar_medicacoes(db: firestore.client, paciente_id: str, consulta_id: str) -> List[Dict]:
    """Lista todas as medicações de uma consulta específica."""
    medicacoes = []
    try:
        query = db.collection('medicacoes') \
                 .where('paciente_id', '==', paciente_id) \
                 .where('consulta_id', '==', consulta_id) \
                 .order_by('created_at', direction=firestore.Query.DESCENDING)
        
        for doc in query.stream():
            medicacao_data = doc.to_dict()
            medicacao_data['id'] = doc.id
            medicacoes.append(medicacao_data)
        
        logger.info(f"Retornando {len(medicacoes)} medicações para a consulta {consulta_id}")
        return medicacoes
    except Exception as e:
        logger.error(f"Erro ao listar medicações da consulta {consulta_id}: {e}")
        return []


def listar_checklist(db: firestore.client, paciente_id: str, consulta_id: str) -> List[Dict]:
    """Lista todos os itens do checklist de uma consulta específica."""
    checklist = []
    try:
        query = db.collection('checklist') \
                 .where('paciente_id', '==', paciente_id) \
                 .where('consulta_id', '==', consulta_id) \
                 .order_by('created_at', direction=firestore.Query.DESCENDING)
        
        for doc in query.stream():
            item_data = doc.to_dict()
            item_data['id'] = doc.id
            checklist.append(item_data)
        
        logger.info(f"Retornando {len(checklist)} itens do checklist para a consulta {consulta_id}")
        return checklist
    except Exception as e:
        logger.error(f"Erro ao listar checklist da consulta {consulta_id}: {e}")
        return []


def criar_exame(db: firestore.client, exame_data: 'schemas.ExameCreate') -> Dict:
    """Cria um novo exame."""
    try:
        exame_dict = exame_data.model_dump()
        exame_dict['created_at'] = firestore.SERVER_TIMESTAMP
        exame_dict['updated_at'] = firestore.SERVER_TIMESTAMP
        
        doc_ref = db.collection('exames').document()
        doc_ref.set(exame_dict)
        
        # Retornar exame criado
        exame_dict['id'] = doc_ref.id
        logger.info(f"Exame criado com ID: {doc_ref.id}")
        return exame_dict
        
    except Exception as e:
        logger.error(f"Erro ao criar exame: {e}")
        raise


def update_exame(db: firestore.client, paciente_id: str, exame_id: str, update_data: 'schemas.ExameUpdate', current_user, negocio_id: str) -> Optional[Dict]:
    """Atualiza um exame específico."""
    try:
        doc_ref = db.collection('exames').document(exame_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            return None
        
        # Verificar se o exame pertence ao paciente
        exame_data = doc.to_dict()
        if exame_data.get('paciente_id') != paciente_id:
            return None
        
        # Atualizar
        update_dict = update_data.model_dump(exclude_unset=True)
        update_dict['updated_at'] = firestore.SERVER_TIMESTAMP
        
        doc_ref.update(update_dict)
        
        # Retornar dados atualizados
        updated_doc = doc_ref.get()
        updated_data = updated_doc.to_dict()
        updated_data['id'] = updated_doc.id
        
        logger.info(f"Exame {exame_id} atualizado")
        return updated_data
        
    except Exception as e:
        logger.error(f"Erro ao atualizar exame {exame_id}: {e}")
        return None


def delete_exame(db: firestore.client, paciente_id: str, exame_id: str) -> bool:
    """Remove um exame."""
    try:
        doc_ref = db.collection('exames').document(exame_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            return False
        
        # Verificar se o exame pertence ao paciente
        exame_data = doc.to_dict()
        if exame_data.get('paciente_id') != paciente_id:
            return False
        
        doc_ref.delete()
        logger.info(f"Exame {exame_id} removido")
        return True
        
    except Exception as e:
        logger.error(f"Erro ao deletar exame {exame_id}: {e}")
        return False


def criar_medicacao(db: firestore.client, medicacao_data: 'schemas.MedicacaoCreate', consulta_id: str) -> Dict:
    """Cria uma nova medicação."""
    try:
        medicacao_dict = medicacao_data.model_dump()
        medicacao_dict['consulta_id'] = consulta_id
        medicacao_dict['created_at'] = firestore.SERVER_TIMESTAMP
        medicacao_dict['updated_at'] = firestore.SERVER_TIMESTAMP
        
        doc_ref = db.collection('medicacoes').document()
        doc_ref.set(medicacao_dict)
        
        # Retornar medicação criada
        medicacao_dict['id'] = doc_ref.id
        logger.info(f"Medicação criada com ID: {doc_ref.id}")
        return medicacao_dict
        
    except Exception as e:
        logger.error(f"Erro ao criar medicação: {e}")
        raise


def criar_checklist_item(db: firestore.client, item_data: 'schemas.ChecklistItemCreate', consulta_id: str) -> Dict:
    """Cria um novo item do checklist."""
    try:
        item_dict = item_data.model_dump()
        item_dict['consulta_id'] = consulta_id
        item_dict['created_at'] = firestore.SERVER_TIMESTAMP
        item_dict['updated_at'] = firestore.SERVER_TIMESTAMP
        
        doc_ref = db.collection('checklist').document()
        doc_ref.set(item_dict)
        
        # Retornar item criado
        item_dict['id'] = doc_ref.id
        logger.info(f"Item do checklist criado com ID: {doc_ref.id}")
        return item_dict
        
    except Exception as e:
        logger.error(f"Erro ao criar item do checklist: {e}")
        raise