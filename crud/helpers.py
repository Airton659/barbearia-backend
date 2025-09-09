# crud/helpers.py
"""
Funções auxiliares e utilitárias internas
"""

import logging
from typing import Optional, List, Dict
from firebase_admin import firestore
from datetime import datetime
import schemas
from crud.utils import add_timestamps

logger = logging.getLogger(__name__)


def _delete_subcollection_item(db: firestore.client, paciente_id: str, collection_name: str, item_id: str) -> bool:
    """Função genérica para deletar um item de uma subcoleção do paciente."""
    try:
        item_ref = db.collection('usuarios').document(paciente_id).collection(collection_name).document(item_id)
        if item_ref.get().exists:
            item_ref.delete()
            logger.info(f"Item {item_id} da coleção {collection_name} do paciente {paciente_id} deletado.")
            return True
        return False
    except Exception as e:
        logger.error(f"Erro ao deletar item {item_id} em {collection_name} do paciente {paciente_id}: {e}")
        return False


def _update_subcollection_item(db: firestore.client, paciente_id: str, collection_name: str, item_id: str, update_data) -> Optional[Dict]:
    """Função genérica para atualizar um item de uma subcoleção do paciente."""
    try:
        item_ref = db.collection('usuarios').document(paciente_id).collection(collection_name).document(item_id)
        item_doc = item_ref.get()
        
        if not item_doc.exists:
            return None
        
        update_dict = update_data.model_dump(exclude_unset=True)
        update_dict['updated_at'] = firestore.SERVER_TIMESTAMP
        
        item_ref.update(update_dict)
        
        updated_doc = item_ref.get()
        updated_data = updated_doc.to_dict()
        updated_data['id'] = updated_doc.id
        
        logger.info(f"Item {item_id} da coleção {collection_name} atualizado")
        return updated_data
        
    except Exception as e:
        logger.error(f"Erro ao atualizar item {item_id} em {collection_name}: {e}")
        return None


def _dedup_checklist_items(items: List[Dict]) -> List[Dict]:
    """Remove itens duplicados do checklist baseado no ID."""
    seen_ids = set()
    unique_items = []
    
    for item in items:
        item_id = item.get('id')
        if item_id not in seen_ids:
            seen_ids.add(item_id)
            unique_items.append(item)
    
    return unique_items


def _detectar_tipo_conteudo(conteudo: str) -> str:
    """Detecta o tipo de conteúdo baseado no texto."""
    conteudo_lower = conteudo.lower()
    
    if any(word in conteudo_lower for word in ['medicamento', 'remedio', 'dosagem', 'prescricao']):
        return 'medicamento'
    elif any(word in conteudo_lower for word in ['exame', 'laboratorio', 'resultado', 'analise']):
        return 'exame'
    elif any(word in conteudo_lower for word in ['sintoma', 'dor', 'febre', 'mal-estar']):
        return 'sintoma'
    elif any(word in conteudo_lower for word in ['orientacao', 'recomendacao', 'cuidado']):
        return 'orientacao'
    else:
        return 'observacao'


def adicionar_exame(db: firestore.client, exame_data: schemas.ExameBase, criador_uid: str) -> Dict:
    """Salva um novo exame, adicionando os campos de auditoria."""
    try:
        exame_dict = exame_data.model_dump(mode='json')
        now = firestore.SERVER_TIMESTAMP
        
        exame_dict['criado_por'] = criador_uid
        exame_dict['created_at'] = now
        exame_dict['updated_at'] = now
        
        doc_ref = db.collection('exames').document()
        doc_ref.set(exame_dict)
        exame_dict['id'] = doc_ref.id
        
        logger.info(f"Exame adicionado para paciente {exame_data.paciente_id}")
        return exame_dict
        
    except Exception as e:
        logger.error(f"Erro ao adicionar exame: {e}")
        raise


def adicionar_item_checklist(db: firestore.client, paciente_id: str, item_data: schemas.ChecklistItemCreate) -> Dict:
    """Adiciona um novo item ao checklist de um paciente."""
    try:
        item_dict = item_data.model_dump()
        item_dict['paciente_id'] = paciente_id
        item_dict = add_timestamps(item_dict, is_update=False)
        
        doc_ref = db.collection('checklist').document()
        doc_ref.set(item_dict)
        item_dict['id'] = doc_ref.id
        
        logger.info(f"Item adicionado ao checklist do paciente {paciente_id}")
        return item_dict
        
    except Exception as e:
        logger.error(f"Erro ao adicionar item ao checklist: {e}")
        raise


def delete_checklist_item(db: firestore.client, paciente_id: str, item_id: str) -> bool:
    """Remove um item do checklist."""
    try:
        item_ref = db.collection('checklist').document(item_id)
        item_doc = item_ref.get()
        
        if not item_doc.exists:
            return False
        
        item_data = item_doc.to_dict()
        if item_data.get('paciente_id') != paciente_id:
            return False
        
        item_ref.delete()
        logger.info(f"Item {item_id} removido do checklist")
        return True
        
    except Exception as e:
        logger.error(f"Erro ao deletar item do checklist: {e}")
        return False


def update_checklist_item(db: firestore.client, paciente_id: str, item_id: str, update_data: schemas.ChecklistItemUpdate) -> Optional[Dict]:
    """Atualiza um item do checklist."""
    try:
        item_ref = db.collection('checklist').document(item_id)
        item_doc = item_ref.get()
        
        if not item_doc.exists:
            return None
        
        item_data = item_doc.to_dict()
        if item_data.get('paciente_id') != paciente_id:
            return None
        
        update_dict = update_data.model_dump(exclude_unset=True)
        update_dict['updated_at'] = firestore.SERVER_TIMESTAMP
        
        item_ref.update(update_dict)
        
        updated_doc = item_ref.get()
        updated_data = updated_doc.to_dict()
        updated_data['id'] = updated_doc.id
        
        logger.info(f"Item checklist {item_id} atualizado")
        return updated_data
        
    except Exception as e:
        logger.error(f"Erro ao atualizar item checklist: {e}")
        return None


def update_consulta(db: firestore.client, paciente_id: str, consulta_id: str, update_data: schemas.ConsultaUpdate) -> Optional[Dict]:
    """Atualiza uma consulta."""
    return _update_subcollection_item(db, paciente_id, "consultas", consulta_id, update_data)


def delete_consulta(db: firestore.client, paciente_id: str, consulta_id: str) -> bool:
    """Remove uma consulta."""
    return _delete_subcollection_item(db, paciente_id, "consultas", consulta_id)


def update_medicacao(db: firestore.client, paciente_id: str, medicacao_id: str, update_data: schemas.MedicacaoUpdate) -> Optional[Dict]:
    """Atualiza uma medicação."""
    try:
        medicacao_ref = db.collection('medicacoes').document(medicacao_id)
        medicacao_doc = medicacao_ref.get()
        
        if not medicacao_doc.exists:
            return None
        
        medicacao_data = medicacao_doc.to_dict()
        if medicacao_data.get('paciente_id') != paciente_id:
            return None
        
        update_dict = update_data.model_dump(exclude_unset=True)
        update_dict['updated_at'] = firestore.SERVER_TIMESTAMP
        
        medicacao_ref.update(update_dict)
        
        updated_doc = medicacao_ref.get()
        updated_data = updated_doc.to_dict()
        updated_data['id'] = updated_doc.id
        
        logger.info(f"Medicação {medicacao_id} atualizada")
        return updated_data
        
    except Exception as e:
        logger.error(f"Erro ao atualizar medicação: {e}")
        return None


def delete_medicacao(db: firestore.client, paciente_id: str, medicacao_id: str) -> bool:
    """Remove uma medicação."""
    try:
        medicacao_ref = db.collection('medicacoes').document(medicacao_id)
        medicacao_doc = medicacao_ref.get()
        
        if not medicacao_doc.exists:
            return False
        
        medicacao_data = medicacao_doc.to_dict()
        if medicacao_data.get('paciente_id') != paciente_id:
            return False
        
        medicacao_ref.delete()
        logger.info(f"Medicação {medicacao_id} removida")
        return True
        
    except Exception as e:
        logger.error(f"Erro ao deletar medicação: {e}")
        return False


def update_orientacao(db: firestore.client, paciente_id: str, orientacao_id: str, update_data: schemas.OrientacaoUpdate) -> Optional[Dict]:
    """Atualiza uma orientação."""
    try:
        orientacao_ref = db.collection('orientacoes').document(orientacao_id)
        orientacao_doc = orientacao_ref.get()
        
        if not orientacao_doc.exists:
            return None
        
        orientacao_data = orientacao_doc.to_dict()
        if orientacao_data.get('paciente_id') != paciente_id:
            return None
        
        update_dict = update_data.model_dump(exclude_unset=True)
        update_dict['updated_at'] = firestore.SERVER_TIMESTAMP
        
        orientacao_ref.update(update_dict)
        
        updated_doc = orientacao_ref.get()
        updated_data = updated_doc.to_dict()
        updated_data['id'] = updated_doc.id
        
        logger.info(f"Orientação {orientacao_id} atualizada")
        return updated_data
        
    except Exception as e:
        logger.error(f"Erro ao atualizar orientação: {e}")
        return None


def delete_orientacao(db: firestore.client, paciente_id: str, orientacao_id: str) -> bool:
    """Remove uma orientação."""
    try:
        orientacao_ref = db.collection('orientacoes').document(orientacao_id)
        orientacao_doc = orientacao_ref.get()
        
        if not orientacao_doc.exists:
            return False
        
        orientacao_data = orientacao_doc.to_dict()
        if orientacao_data.get('paciente_id') != paciente_id:
            return False
        
        orientacao_ref.delete()
        logger.info(f"Orientação {orientacao_id} removida")
        return True
        
    except Exception as e:
        logger.error(f"Erro ao deletar orientação: {e}")
        return False


def prescrever_medicacao(db: firestore.client, prescricao_data: schemas.PrescricaoCreate, medico_id: str) -> Dict:
    """Prescreve uma medicação para um paciente."""
    try:
        prescricao_dict = prescricao_data.model_dump()
        prescricao_dict['medico_id'] = medico_id
        prescricao_dict['status'] = 'ativa'
        prescricao_dict = add_timestamps(prescricao_dict, is_update=False)
        
        doc_ref = db.collection('prescricoes').document()
        doc_ref.set(prescricao_dict)
        prescricao_dict['id'] = doc_ref.id
        
        logger.info(f"Medicação prescrita para paciente {prescricao_data.paciente_id}")
        return prescricao_dict
        
    except Exception as e:
        logger.error(f"Erro ao prescrever medicação: {e}")
        raise


def criar_log_auditoria(db: firestore.client, acao: str, usuario_id: str, detalhes: Dict) -> Dict:
    """Cria um log de auditoria para rastreamento de ações."""
    try:
        log_dict = {
            'acao': acao,
            'usuario_id': usuario_id,
            'detalhes': detalhes,
            'timestamp': firestore.SERVER_TIMESTAMP,
            'ip_address': detalhes.get('ip_address'),
            'user_agent': detalhes.get('user_agent')
        }
        
        doc_ref = db.collection('logs_auditoria').document()
        doc_ref.set(log_dict)
        log_dict['id'] = doc_ref.id
        
        logger.info(f"Log de auditoria criado: {acao} por {usuario_id}")
        return log_dict
        
    except Exception as e:
        logger.error(f"Erro ao criar log de auditoria: {e}")
        raise


def registrar_confirmacao_leitura_plano(db: firestore.client, paciente_id: str, plano_id: str, data_leitura: datetime) -> bool:
    """Registra a confirmação de leitura de um plano pelo paciente."""
    try:
        confirmacao_dict = {
            'paciente_id': paciente_id,
            'plano_id': plano_id,
            'data_leitura': data_leitura,
            'confirmado': True,
            'created_at': firestore.SERVER_TIMESTAMP
        }
        
        doc_ref = db.collection('confirmacoes_leitura').document()
        doc_ref.set(confirmacao_dict)
        
        logger.info(f"Confirmação de leitura registrada para plano {plano_id}")
        return True
        
    except Exception as e:
        logger.error(f"Erro ao registrar confirmação de leitura: {e}")
        return False


def verificar_leitura_plano_do_dia(db: firestore.client, paciente_id: str, data: datetime.date) -> bool:
    """Verifica se o paciente já leu o plano do dia."""
    try:
        query = db.collection('confirmacoes_leitura') \
                 .where('paciente_id', '==', paciente_id) \
                 .where('data_leitura', '>=', data) \
                 .where('data_leitura', '<', data + datetime.timedelta(days=1))
        
        confirmacoes = list(query.stream())
        return len(confirmacoes) > 0
        
    except Exception as e:
        logger.error(f"Erro ao verificar leitura do plano: {e}")
        return False