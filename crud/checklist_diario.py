# crud/checklist_diario.py
"""
CRUD para gestão de checklist diário e registros
"""

import logging
from typing import Optional, List, Dict
from firebase_admin import firestore
from datetime import date, datetime
import schemas
from crud.utils import add_timestamps

logger = logging.getLogger(__name__)


def criar_registro_diario(db: firestore.client, registro_data: schemas.DiarioTecnicoCreate, tecnico: schemas.UsuarioProfile) -> Dict:
    """Cria um novo registro diário."""
    try:
        registro_dict = {
            'paciente_id': registro_data.paciente_id,
            'tecnico_id': tecnico.id,
            'tecnico_nome': tecnico.nome,
            'data_registro': registro_data.data_registro,
            'titulo': registro_data.titulo,
            'conteudo': registro_data.conteudo,
            'tipo': registro_data.tipo or 'observacao',
            'prioridade': registro_data.prioridade or 'normal',
            'categoria': registro_data.categoria,
            'tags': registro_data.tags or [],
            'anexos': registro_data.anexos or []
        }
        
        registro_dict = add_timestamps(registro_dict, is_update=False)
        
        doc_ref = db.collection('registros_diarios').document()
        doc_ref.set(registro_dict)
        registro_dict['id'] = doc_ref.id
        
        logger.info(f"Registro diário criado para paciente {registro_data.paciente_id}")
        return registro_dict
        
    except Exception as e:
        logger.error(f"Erro ao criar registro diário: {e}")
        raise


def listar_registros_diario(db: firestore.client, paciente_id: str) -> List[Dict]:
    """Lista todos os registros diários de um paciente."""
    registros = []
    try:
        query = db.collection('registros_diarios') \
                 .where('paciente_id', '==', paciente_id) \
                 .order_by('data_registro', direction=firestore.Query.DESCENDING)
        
        for doc in query.stream():
            registro_data = doc.to_dict()
            registro_data['id'] = doc.id
            registros.append(registro_data)
        
        logger.info(f"Retornando {len(registros)} registros diários para paciente {paciente_id}")
        return registros
        
    except Exception as e:
        logger.error(f"Erro ao listar registros diários: {e}")
        return []


def update_registro_diario(db: firestore.client, paciente_id: str, registro_id: str, update_data: schemas.DiarioTecnicoUpdate, tecnico_id: str) -> Optional[Dict]:
    """Atualiza um registro diário."""
    try:
        registro_ref = db.collection('registros_diarios').document(registro_id)
        registro_doc = registro_ref.get()
        
        if not registro_doc.exists:
            return None
        
        registro_data = registro_doc.to_dict()
        
        # Verificar permissões
        if registro_data.get('paciente_id') != paciente_id:
            return None
        
        if registro_data.get('tecnico_id') != tecnico_id:
            return None
        
        update_dict = update_data.model_dump(exclude_unset=True)
        update_dict['updated_at'] = firestore.SERVER_TIMESTAMP
        
        registro_ref.update(update_dict)
        
        updated_doc = registro_ref.get()
        updated_data = updated_doc.to_dict()
        updated_data['id'] = updated_doc.id
        
        logger.info(f"Registro diário {registro_id} atualizado")
        return updated_data
        
    except Exception as e:
        logger.error(f"Erro ao atualizar registro diário: {e}")
        return None


def delete_registro_diario(db: firestore.client, paciente_id: str, registro_id: str, tecnico_id: str) -> bool:
    """Remove um registro diário."""
    try:
        registro_ref = db.collection('registros_diarios').document(registro_id)
        registro_doc = registro_ref.get()
        
        if not registro_doc.exists:
            return False
        
        registro_data = registro_doc.to_dict()
        
        # Verificar permissões
        if registro_data.get('paciente_id') != paciente_id:
            return False
        
        if registro_data.get('tecnico_id') != tecnico_id:
            return False
        
        registro_ref.delete()
        logger.info(f"Registro diário {registro_id} removido")
        return True
        
    except Exception as e:
        logger.error(f"Erro ao deletar registro diário: {e}")
        return False


def adicionar_registro_diario(db: firestore.client, paciente_id: str, registro: schemas.RegistroDiarioCreate, tecnico_id: str) -> Dict:
    """Adiciona um registro diário simplificado."""
    try:
        registro_dict = {
            'paciente_id': paciente_id,
            'tecnico_id': tecnico_id,
            'data_registro': registro.data_registro,
            'observacoes': registro.observacoes,
            'humor': registro.humor,
            'sintomas': registro.sintomas or [],
            'medicamentos_tomados': registro.medicamentos_tomados or []
        }
        
        registro_dict = add_timestamps(registro_dict, is_update=False)
        
        doc_ref = db.collection('registros_diarios_simples').document()
        doc_ref.set(registro_dict)
        registro_dict['id'] = doc_ref.id
        
        logger.info(f"Registro diário simples criado para paciente {paciente_id}")
        return registro_dict
        
    except Exception as e:
        logger.error(f"Erro ao adicionar registro diário: {e}")
        raise


def listar_checklist_diario(db: firestore.client, paciente_id: str, dia: date, negocio_id: str) -> List[Dict]:
    """Lista o checklist diário de um paciente para um dia específico."""
    checklist = []
    try:
        query = db.collection('checklist_diario') \
                 .where('paciente_id', '==', paciente_id) \
                 .where('data', '==', dia.isoformat()) \
                 .where('negocio_id', '==', negocio_id)
        
        for doc in query.stream():
            item_data = doc.to_dict()
            item_data['id'] = doc.id
            checklist.append(item_data)
        
        logger.info(f"Retornando {len(checklist)} itens do checklist diário para {dia}")
        return checklist
        
    except Exception as e:
        logger.error(f"Erro ao listar checklist diário: {e}")
        return []


def atualizar_item_checklist_diario(db: firestore.client, paciente_id: str, data: date, item_id: str, update_data: schemas.ChecklistItemDiarioUpdate) -> Optional[Dict]:
    """Atualiza um item do checklist diário."""
    try:
        item_ref = db.collection('checklist_diario').document(item_id)
        item_doc = item_ref.get()
        
        if not item_doc.exists:
            return None
        
        item_data = item_doc.to_dict()
        
        # Verificar se pertence ao paciente
        if item_data.get('paciente_id') != paciente_id:
            return None
        
        update_dict = update_data.model_dump(exclude_unset=True)
        update_dict['updated_at'] = firestore.SERVER_TIMESTAMP
        
        item_ref.update(update_dict)
        
        updated_doc = item_ref.get()
        updated_data = updated_doc.to_dict()
        updated_data['id'] = updated_doc.id
        
        logger.info(f"Item checklist diário {item_id} atualizado")
        return updated_data
        
    except Exception as e:
        logger.error(f"Erro ao atualizar item checklist diário: {e}")
        return None


def listar_checklist_diario_com_replicacao(db: firestore.client, paciente_id: str, dia: date, negocio_id: str) -> List[Dict]:
    """Lista checklist diário com replicação de itens do plano ativo."""
    try:
        # Primeiro, buscar checklist existente para o dia
        checklist_existente = listar_checklist_diario(db, paciente_id, dia, negocio_id)
        
        if checklist_existente:
            return checklist_existente
        
        # Se não existe, buscar do plano ativo e replicar
        checklist_plano = get_checklist_diario_plano_ativo(db, paciente_id, dia, negocio_id)
        
        if checklist_plano:
            checklist_replicado = []
            
            for item_plano in checklist_plano:
                item_dict = {
                    'paciente_id': paciente_id,
                    'negocio_id': negocio_id,
                    'data': dia.isoformat(),
                    'descricao': item_plano.get('descricao'),
                    'horario': item_plano.get('horario'),
                    'concluido': False,
                    'observacoes': '',
                    'plano_item_id': item_plano.get('id')
                }
                
                item_dict = add_timestamps(item_dict, is_update=False)
                
                doc_ref = db.collection('checklist_diario').document()
                doc_ref.set(item_dict)
                item_dict['id'] = doc_ref.id
                
                checklist_replicado.append(item_dict)
            
            logger.info(f"Checklist diário replicado para {dia}: {len(checklist_replicado)} itens")
            return checklist_replicado
        
        return []
        
    except Exception as e:
        logger.error(f"Erro ao listar checklist com replicação: {e}")
        return []


def get_checklist_diario_plano_ativo(db: firestore.client, paciente_id: str, dia: date, negocio_id: str) -> List[Dict]:
    """Busca o checklist diário do plano ativo do paciente."""
    try:
        # Buscar plano ativo do paciente
        planos_query = db.collection('planos_tratamento') \
                        .where('paciente_id', '==', paciente_id) \
                        .where('negocio_id', '==', negocio_id) \
                        .where('ativo', '==', True) \
                        .limit(1)
        
        planos = list(planos_query.stream())
        if not planos:
            return []
        
        plano_ativo = planos[0].to_dict()
        plano_id = planos[0].id
        
        # Buscar checklist do plano
        checklist_query = db.collection('planos_tratamento') \
                          .document(plano_id) \
                          .collection('checklist_diario')
        
        checklist = []
        for doc in checklist_query.stream():
            item_data = doc.to_dict()
            item_data['id'] = doc.id
            checklist.append(item_data)
        
        logger.info(f"Retornando {len(checklist)} itens do plano ativo para checklist diário")
        return checklist
        
    except Exception as e:
        logger.error(f"Erro ao buscar checklist do plano ativo: {e}")
        return []


def criar_registro_diario_estruturado(db: firestore.client, registro_data: schemas.RegistroDiarioCreate, tecnico_id: str) -> Dict:
    """Cria um registro diário estruturado."""
    try:
        registro_dict = {
            'paciente_id': registro_data.paciente_id,
            'tecnico_id': tecnico_id,
            'data_registro': registro_data.data_registro,
            'observacoes': registro_data.observacoes,
            'humor': registro_data.humor,
            'sintomas': registro_data.sintomas or [],
            'medicamentos': registro_data.medicamentos_tomados or [],
            'atividades': registro_data.atividades or [],
            'sono': registro_data.sono,
            'alimentacao': registro_data.alimentacao,
            'outros_dados': registro_data.outros_dados or {}
        }
        
        registro_dict = add_timestamps(registro_dict, is_update=False)
        
        doc_ref = db.collection('registros_diarios_estruturados').document()
        doc_ref.set(registro_dict)
        registro_dict['id'] = doc_ref.id
        
        logger.info(f"Registro diário estruturado criado para paciente {registro_data.paciente_id}")
        return registro_dict
        
    except Exception as e:
        logger.error(f"Erro ao criar registro estruturado: {e}")
        raise


def listar_registros_diario_estruturado(db: firestore.client, paciente_id: str, data_inicio: Optional[date] = None, data_fim: Optional[date] = None) -> List[Dict]:
    """Lista registros diários estruturados com filtro de data."""
    registros = []
    try:
        query = db.collection('registros_diarios_estruturados') \
                 .where('paciente_id', '==', paciente_id)
        
        if data_inicio:
            query = query.where('data_registro', '>=', data_inicio.isoformat())
        
        if data_fim:
            query = query.where('data_registro', '<=', data_fim.isoformat())
        
        query = query.order_by('data_registro', direction=firestore.Query.DESCENDING)
        
        for doc in query.stream():
            registro_data = doc.to_dict()
            registro_data['id'] = doc.id
            registros.append(registro_data)
        
        logger.info(f"Retornando {len(registros)} registros estruturados")
        return registros
        
    except Exception as e:
        logger.error(f"Erro ao listar registros estruturados: {e}")
        return []


def atualizar_registro_diario_estruturado(db: firestore.client, registro_id: str, update_data: schemas.RegistroDiarioUpdate, tecnico_id: str) -> Optional[Dict]:
    """Atualiza um registro diário estruturado."""
    try:
        registro_ref = db.collection('registros_diarios_estruturados').document(registro_id)
        registro_doc = registro_ref.get()
        
        if not registro_doc.exists:
            return None
        
        registro_data = registro_doc.to_dict()
        
        # Verificar se o técnico pode editar
        if registro_data.get('tecnico_id') != tecnico_id:
            return None
        
        update_dict = update_data.model_dump(exclude_unset=True)
        update_dict['updated_at'] = firestore.SERVER_TIMESTAMP
        
        registro_ref.update(update_dict)
        
        updated_doc = registro_ref.get()
        updated_data = updated_doc.to_dict()
        updated_data['id'] = updated_doc.id
        
        logger.info(f"Registro estruturado {registro_id} atualizado")
        return updated_data
        
    except Exception as e:
        logger.error(f"Erro ao atualizar registro estruturado: {e}")
        return None


def deletar_registro_diario_estruturado(db: firestore.client, registro_id: str, tecnico_id: str) -> bool:
    """Remove um registro diário estruturado."""
    try:
        registro_ref = db.collection('registros_diarios_estruturados').document(registro_id)
        registro_doc = registro_ref.get()
        
        if not registro_doc.exists:
            return False
        
        registro_data = registro_doc.to_dict()
        
        # Verificar se o técnico pode deletar
        if registro_data.get('tecnico_id') != tecnico_id:
            return False
        
        registro_ref.delete()
        logger.info(f"Registro estruturado {registro_id} removido")
        return True
        
    except Exception as e:
        logger.error(f"Erro ao deletar registro estruturado: {e}")
        return False


def atualizar_item_checklist_diario(db: firestore.client, paciente_id: str, item_id: str, update_data: schemas.ChecklistItemDiarioUpdate) -> Optional[Dict]:
    """Atualiza um item do checklist diário (versão sem data)."""
    try:
        item_ref = db.collection('checklist_diario').document(item_id)
        item_doc = item_ref.get()
        
        if not item_doc.exists:
            return None
        
        item_data = item_doc.to_dict()
        
        # Verificar se pertence ao paciente
        if item_data.get('paciente_id') != paciente_id:
            return None
        
        update_dict = update_data.model_dump(exclude_unset=True)
        update_dict['updated_at'] = firestore.SERVER_TIMESTAMP
        
        item_ref.update(update_dict)
        
        updated_doc = item_ref.get()
        updated_data = updated_doc.to_dict()
        updated_data['id'] = updated_doc.id
        
        logger.info(f"Item checklist diário {item_id} atualizado")
        return updated_data
        
    except Exception as e:
        logger.error(f"Erro ao atualizar item checklist diário: {e}")
        return None