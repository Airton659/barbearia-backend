# crud/agendamentos.py
"""
CRUD para gestão de agendamentos
"""

from __future__ import annotations
import logging
from typing import Optional, List, Dict
from firebase_admin import firestore
import schemas
from datetime import datetime, timedelta
from crud.utils import add_timestamps
from crud.profissionais import buscar_profissional_por_id
from crud.usuarios import buscar_usuario_por_firebase_uid
from crud.notifications import _send_data_push_to_tokens, _notificar_cliente_cancelamento
from crypto_utils import decrypt_data

logger = logging.getLogger(__name__)


def criar_agendamento(db: firestore.client, agendamento_data: schemas.AgendamentoCreate, cliente: schemas.UsuarioProfile) -> Dict:
    """Cria um novo agendamento, desnormalizando os dados necessários."""
    
    profissional = buscar_profissional_por_id(db, agendamento_data.profissional_id)
    servico_doc = db.collection('servicos').document(agendamento_data.servico_id).get()

    if not profissional or not servico_doc.exists:
        raise ValueError("Profissional ou serviço não encontrado.")

    servico = servico_doc.to_dict()

    agendamento_dict = {
        "negocio_id": agendamento_data.negocio_id,
        "data_hora": agendamento_data.data_hora,
        "status": "pendente",
        "cliente_id": cliente.id,
        "cliente_nome": cliente.nome,
        "profissional_id": profissional['id'],
        "profissional_nome": profissional['nome'],
        "profissional_foto_thumbnail": profissional.get('fotos', {}).get('thumbnail'),
        "servico_id": agendamento_data.servico_id,
        "servico_nome": servico['nome'],
        "servico_preco": servico['preco'],
        "servico_duracao_minutos": servico['duracao_minutos']
    }

    doc_ref = db.collection('agendamentos').document()
    doc_ref.set(agendamento_dict)
    
    agendamento_dict['id'] = doc_ref.id
    
    # --- INÍCIO DA LÓGICA DE NOTIFICAÇÃO ---
    prof_user = buscar_usuario_por_firebase_uid(db, profissional['usuario_uid'])
    if prof_user: # Verifica se o usuário profissional existe
        data_formatada = agendamento_data.data_hora.strftime('%d/%m/%Y')
        hora_formatada = agendamento_data.data_hora.strftime('%H:%M')
        mensagem_body = f"Você tem um novo agendamento com {cliente.nome} para o dia {data_formatada} às {hora_formatada}."
        
        # 1. Persistir a notificação no Firestore
        try:
            notificacao_id = f"NOVO_AGENDAMENTO:{doc_ref.id}"
            dedupe_key = notificacao_id
            
            notificacao_doc_ref = db.collection('usuarios').document(prof_user['id']).collection('notificacoes').document(notificacao_id)
            
            notificacao_doc_ref.set({
                "title": "Novo Agendamento!",
                "body": mensagem_body,
                "tipo": "NOVO_AGENDAMENTO",
                "relacionado": { "agendamento_id": doc_ref.id },
                "lida": False,
                "data_criacao": firestore.SERVER_TIMESTAMP,
                "dedupe_key": dedupe_key
            })
            logger.info(f"Notificação de novo agendamento PERSISTIDA para o profissional {profissional['id']}.")
        except Exception as e:
            logger.error(f"Erro ao PERSISTIR notificação de novo agendamento: {e}")

        # 2. Enviar a notificação via FCM, se houver tokens
        if prof_user.get('fcm_tokens'):
            data_payload = {
                "title": "Novo Agendamento!",
                "body": mensagem_body,
                "tipo": "NOVO_AGENDAMENTO",
                "agendamento_id": doc_ref.id
            }
            try:
                _send_data_push_to_tokens(
                    db=db,
                    firebase_uid_destinatario=profissional['usuario_uid'],
                    tokens=prof_user['fcm_tokens'],
                    data_dict=data_payload,
                    logger_prefix="[Novo agendamento] "
                )
            except Exception as e:
                logger.error(f"Erro ao ENVIAR notificação de novo agendamento: {e}")
    # --- FIM DA LÓGICA DE NOTIFICAÇÃO ---

    return agendamento_dict


def listar_agendamentos_por_cliente(db: firestore.client, negocio_id: str, cliente_id: str) -> List[Dict]:
    """Lista os agendamentos de um cliente em um negócio específico."""
    agendamentos = []
    query = db.collection('agendamentos').where('negocio_id', '==', negocio_id).where('cliente_id', '==', cliente_id).order_by('data_hora', direction=firestore.Query.DESCENDING)
    
    for doc in query.stream():
        ag_data = doc.to_dict()
        ag_data['id'] = doc.id
        
        # Descriptografa nomes se presentes
        if 'cliente_nome' in ag_data and ag_data['cliente_nome']:
            try:
                ag_data['cliente_nome'] = decrypt_data(ag_data['cliente_nome'])
            except Exception as e:
                logger.error(f"Erro ao descriptografar cliente_nome no agendamento {doc.id}: {e}")
                ag_data['cliente_nome'] = "[Erro na descriptografia]"
        
        if 'profissional_nome' in ag_data and ag_data['profissional_nome']:
            try:
                ag_data['profissional_nome'] = decrypt_data(ag_data['profissional_nome'])
            except Exception as e:
                logger.error(f"Erro ao descriptografar profissional_nome no agendamento {doc.id}: {e}")
                ag_data['profissional_nome'] = "[Erro na descriptografia]"
        
        agendamentos.append(ag_data)
    
    return agendamentos


def listar_agendamentos_por_profissional(db: firestore.client, negocio_id: str, profissional_id: str) -> List[Dict]:
    """Lista os agendamentos de um profissional em um negócio específico."""
    agendamentos = []
    query = db.collection('agendamentos').where('negocio_id', '==', negocio_id).where('profissional_id', '==', profissional_id).order_by('data_hora', direction=firestore.Query.DESCENDING)
    
    for doc in query.stream():
        ag_data = doc.to_dict()
        ag_data['id'] = doc.id
        
        # Descriptografa nomes se presentes
        if 'cliente_nome' in ag_data and ag_data['cliente_nome']:
            try:
                ag_data['cliente_nome'] = decrypt_data(ag_data['cliente_nome'])
            except Exception as e:
                logger.error(f"Erro ao descriptografar cliente_nome no agendamento {doc.id}: {e}")
                ag_data['cliente_nome'] = "[Erro na descriptografia]"
        
        if 'profissional_nome' in ag_data and ag_data['profissional_nome']:
            try:
                ag_data['profissional_nome'] = decrypt_data(ag_data['profissional_nome'])
            except Exception as e:
                logger.error(f"Erro ao descriptografar profissional_nome no agendamento {doc.id}: {e}")
                ag_data['profissional_nome'] = "[Erro na descriptografia]"
        
        agendamentos.append(ag_data)
        
    return agendamentos


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


def cancelar_agendamento(db: firestore.client, agendamento_id: str, cliente_id: str) -> Optional[Dict]:
    """
    Cancela um agendamento a pedido do cliente, atualizando seu status.
    Envia uma notificação para o profissional.
    """
    agendamento_ref = db.collection('agendamentos').document(agendamento_id)
    agendamento_doc = agendamento_ref.get()

    if not agendamento_doc.exists:
        return None
    
    agendamento = agendamento_doc.to_dict()
    
    if agendamento.get('cliente_id') != cliente_id:
        return None
    
    agendamento_ref.update({"status": "cancelado_pelo_cliente"})
    agendamento["status"] = "cancelado_pelo_cliente"
        
    profissional = buscar_profissional_por_id(db, agendamento['profissional_id'])
    if profissional:
        prof_user = buscar_usuario_por_firebase_uid(db, profissional['usuario_uid'])
        if prof_user:
            data_formatada = agendamento['data_hora'].strftime('%d/%m')
            hora_formatada = agendamento['data_hora'].strftime('%H:%M')
            mensagem_body = f"O cliente {agendamento['cliente_nome']} cancelou o horário das {hora_formatada} do dia {data_formatada}."

            # 1. Persistir a notificação no Firestore
            try:
                notificacao_id = f"AGENDAMENTO_CANCELADO_CLIENTE:{agendamento_id}"
                dedupe_key = notificacao_id
                
                notificacao_doc_ref = db.collection('usuarios').document(prof_user['id']).collection('notificacoes').document(notificacao_id)
                
                notificacao_doc_ref.set({
                    "title": "Agendamento Cancelado",
                    "body": mensagem_body,
                    "tipo": "AGENDAMENTO_CANCELADO_CLIENTE",
                    "relacionado": { "agendamento_id": agendamento_id },
                    "lida": False,
                    "data_criacao": firestore.SERVER_TIMESTAMP,
                    "dedupe_key": dedupe_key
                })
                logger.info(f"Notificação de cancelamento pelo cliente PERSISTIDA para o profissional {profissional['id']}.")
            except Exception as e:
                logger.error(f"Erro ao PERSISTIR notificação de cancelamento pelo cliente: {e}")

            # 2. Enviar a notificação via FCM, se houver tokens
            if prof_user.get('fcm_tokens'):
                data_payload = {
                    "title": "Agendamento Cancelado",
                    "body": mensagem_body,
                    "tipo": "AGENDAMENTO_CANCELADO_CLIENTE"
                }
                try:
                    _send_data_push_to_tokens(
                        db=db,
                        firebase_uid_destinatario=profissional['usuario_uid'],
                        tokens=prof_user['fcm_tokens'],
                        data_dict=data_payload,
                        logger_prefix="[Cancelamento pelo cliente] "
                    )
                except Exception as e:
                    logger.error(f"Erro ao ENVIAR notificação de cancelamento para o profissional {profissional['id']}: {e}")

    return agendamento


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


def cancelar_agendamento_pelo_profissional(db: firestore.client, agendamento_id: str, profissional_id: str) -> Optional[Dict]:
    """
    Permite a um profissional cancelar um agendamento, atualizando o status
    e notificando o cliente.
    """
    agendamento_ref = db.collection('agendamentos').document(agendamento_id)
    agendamento_doc = agendamento_ref.get()

    if not agendamento_doc.exists:
        logger.warning(f"Tentativa de cancelar agendamento inexistente: {agendamento_id}")
        return None
    
    agendamento = agendamento_doc.to_dict()
    agendamento['id'] = agendamento_doc.id

    if agendamento.get('profissional_id') != profissional_id:
        logger.warning(f"Profissional {profissional_id} tentou cancelar agendamento {agendamento_id} sem permissão.")
        return None  # Profissional não autorizado

    # Atualiza o status
    agendamento_ref.update({"status": "cancelado_pelo_profissional"})
    agendamento["status"] = "cancelado_pelo_profissional"
    logger.info(f"Agendamento {agendamento_id} cancelado pelo profissional {profissional_id}.")
    
    # Dispara a notificação para o cliente
    _notificar_cliente_cancelamento(db, agendamento, agendamento_id)
    
    return agendamento


def definir_horarios_trabalho(db: firestore.client, profissional_id: str, horarios: List[schemas.HorarioTrabalho]):
    """Define os horários de trabalho para um profissional, substituindo os existentes."""
    try:
        # Remover horários existentes
        query = db.collection('horarios_trabalho').where('profissional_id', '==', profissional_id)
        batch = db.batch()
        
        for doc in query.stream():
            batch.delete(doc.reference)
        batch.commit()
        
        # Adicionar novos horários
        for horario in horarios:
            horario_dict = {
                "profissional_id": profissional_id,
                "dia_semana": horario.dia_semana,
                "hora_inicio": horario.hora_inicio.isoformat(),
                "hora_fim": horario.hora_fim.isoformat()
            }
            horario_dict = add_timestamps(horario_dict, is_update=False)
            
            doc_ref = db.collection('horarios_trabalho').document()
            doc_ref.set(horario_dict)
        
        logger.info(f"Horários de trabalho definidos para profissional {profissional_id}")
        return listar_horarios_trabalho(db, profissional_id)
        
    except Exception as e:
        logger.error(f"Erro ao definir horários de trabalho: {e}")
        raise