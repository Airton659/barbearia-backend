# crud/agendamentos.py
"""
CRUD para gestão de agendamentos
"""

import logging
from typing import Optional, List, Dict
from firebase_admin import firestore
import schemas
from datetime import datetime, timedelta
from crud.utils import add_timestamps

logger = logging.getLogger(__name__)


def criar_agendamento(db: firestore.client, agendamento_data: schemas.AgendamentoCreate, cliente: schemas.UsuarioProfile) -> Dict:
    """Cria um novo agendamento."""
    try:
        # Preparar dados do agendamento
        agendamento_dict = {
            'negocio_id': agendamento_data.negocio_id,
            'profissional_id': agendamento_data.profissional_id,
            'servico_id': agendamento_data.servico_id,
            'cliente_id': cliente.id,
            'cliente_nome': cliente.nome,
            'cliente_email': cliente.email,
            'data_hora': agendamento_data.data_hora,
            'duracao_minutos': agendamento_data.duracao_minutos,
            'preco': agendamento_data.preco,
            'status': 'agendado',
            'observacoes': agendamento_data.observacoes or '',
        }
        
        # Adicionar timestamps
        agendamento_dict = add_timestamps(agendamento_dict, is_update=False)
        
        # Salvar no Firestore
        doc_ref = db.collection('agendamentos').document()
        doc_ref.set(agendamento_dict)
        agendamento_dict['id'] = doc_ref.id
        
        logger.info(f"Agendamento criado para cliente {cliente.nome} com profissional {agendamento_data.profissional_id}")
        return agendamento_dict
        
    except Exception as e:
        logger.error(f"Erro ao criar agendamento: {e}")
        raise


def listar_agendamentos_por_cliente(db: firestore.client, negocio_id: str, cliente_id: str) -> List[Dict]:
    """Lista todos os agendamentos de um cliente."""
    agendamentos = []
    try:
        query = db.collection('agendamentos') \
                 .where('negocio_id', '==', negocio_id) \
                 .where('cliente_id', '==', cliente_id) \
                 .order_by('data_hora', direction=firestore.Query.DESCENDING)
        
        for doc in query.stream():
            agendamento_data = doc.to_dict()
            agendamento_data['id'] = doc.id
            agendamentos.append(agendamento_data)
        
        logger.info(f"Retornando {len(agendamentos)} agendamentos para o cliente {cliente_id}")
        return agendamentos
    except Exception as e:
        logger.error(f"Erro ao listar agendamentos do cliente {cliente_id}: {e}")
        return []


def listar_agendamentos_por_profissional(db: firestore.client, negocio_id: str, profissional_id: str) -> List[Dict]:
    """Lista todos os agendamentos de um profissional."""
    agendamentos = []
    try:
        query = db.collection('agendamentos') \
                 .where('negocio_id', '==', negocio_id) \
                 .where('profissional_id', '==', profissional_id) \
                 .order_by('data_hora', direction=firestore.Query.ASCENDING)
        
        for doc in query.stream():
            agendamento_data = doc.to_dict()
            agendamento_data['id'] = doc.id
            agendamentos.append(agendamento_data)
        
        logger.info(f"Retornando {len(agendamentos)} agendamentos para o profissional {profissional_id}")
        return agendamentos
    except Exception as e:
        logger.error(f"Erro ao listar agendamentos do profissional {profissional_id}: {e}")
        return []


def atualizar_agendamento(db: firestore.client, agendamento_id: str, update_data: schemas.AgendamentoUpdate) -> Optional[Dict]:
    """Atualiza um agendamento."""
    try:
        agendamento_ref = db.collection('agendamentos').document(agendamento_id)
        agendamento_doc = agendamento_ref.get()
        
        if not agendamento_doc.exists:
            logger.warning(f"Agendamento {agendamento_id} não encontrado")
            return None
        
        # Preparar dados para atualização
        update_dict = update_data.model_dump(exclude_unset=True)
        update_dict['updated_at'] = firestore.SERVER_TIMESTAMP
        
        # Atualizar
        agendamento_ref.update(update_dict)
        
        # Retornar dados atualizados
        updated_doc = agendamento_ref.get()
        updated_data = updated_doc.to_dict()
        updated_data['id'] = updated_doc.id
        
        logger.info(f"Agendamento {agendamento_id} atualizado com sucesso")
        return updated_data
        
    except Exception as e:
        logger.error(f"Erro ao atualizar agendamento {agendamento_id}: {e}")
        return None


def cancelar_agendamento(db: firestore.client, agendamento_id: str, motivo_cancelamento: Optional[str] = None) -> bool:
    """Cancela um agendamento."""
    try:
        agendamento_ref = db.collection('agendamentos').document(agendamento_id)
        agendamento_doc = agendamento_ref.get()
        
        if not agendamento_doc.exists:
            logger.warning(f"Agendamento {agendamento_id} não encontrado")
            return False
        
        # Atualizar status para cancelado
        update_dict = {
            'status': 'cancelado',
            'data_cancelamento': firestore.SERVER_TIMESTAMP,
            'updated_at': firestore.SERVER_TIMESTAMP
        }
        
        if motivo_cancelamento:
            update_dict['motivo_cancelamento'] = motivo_cancelamento
        
        agendamento_ref.update(update_dict)
        
        logger.info(f"Agendamento {agendamento_id} cancelado com sucesso")
        return True
        
    except Exception as e:
        logger.error(f"Erro ao cancelar agendamento {agendamento_id}: {e}")
        return False


def listar_horarios_trabalho(db: firestore.client, profissional_id: str) -> List[Dict]:
    """Lista os horários de trabalho de um profissional."""
    horarios = []
    try:
        query = db.collection('horarios_trabalho').where('profissional_id', '==', profissional_id)
        
        for doc in query.stream():
            horario_data = doc.to_dict()
            horario_data['id'] = doc.id
            horarios.append(horario_data)
        
        logger.info(f"Retornando {len(horarios)} horários de trabalho para o profissional {profissional_id}")
        return horarios
    except Exception as e:
        logger.error(f"Erro ao listar horários de trabalho do profissional {profissional_id}: {e}")
        return []


def criar_bloqueio(db: firestore.client, profissional_id: str, bloqueio_data: schemas.Bloqueio) -> Dict:
    """Cria um bloqueio de horário para um profissional."""
    try:
        # Preparar dados do bloqueio
        bloqueio_dict = {
            'profissional_id': profissional_id,
            'data_inicio': bloqueio_data.data_inicio,
            'data_fim': bloqueio_data.data_fim,
            'motivo': bloqueio_data.motivo,
            'ativo': True
        }
        
        # Adicionar timestamps
        bloqueio_dict = add_timestamps(bloqueio_dict, is_update=False)
        
        # Salvar no Firestore
        doc_ref = db.collection('bloqueios').document()
        doc_ref.set(bloqueio_dict)
        bloqueio_dict['id'] = doc_ref.id
        
        logger.info(f"Bloqueio criado para profissional {profissional_id}")
        return bloqueio_dict
        
    except Exception as e:
        logger.error(f"Erro ao criar bloqueio: {e}")
        raise


def deletar_bloqueio(db: firestore.client, profissional_id: str, bloqueio_id: str) -> bool:
    """Remove um bloqueio de horário."""
    try:
        bloqueio_ref = db.collection('bloqueios').document(bloqueio_id)
        bloqueio_doc = bloqueio_ref.get()
        
        if not bloqueio_doc.exists:
            logger.warning(f"Bloqueio {bloqueio_id} não encontrado")
            return False
        
        bloqueio_data = bloqueio_doc.to_dict()
        
        # Verificar se o bloqueio pertence ao profissional
        if bloqueio_data.get('profissional_id') != profissional_id:
            logger.warning(f"Bloqueio {bloqueio_id} não pertence ao profissional {profissional_id}")
            return False
        
        # Remover bloqueio
        bloqueio_ref.delete()
        
        logger.info(f"Bloqueio {bloqueio_id} removido com sucesso")
        return True
        
    except Exception as e:
        logger.error(f"Erro ao remover bloqueio {bloqueio_id}: {e}")
        return False