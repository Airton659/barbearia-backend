# crud/notifications.py
"""
CRUD para gestão de notificações e FCM tokens
"""

import logging
from typing import Optional, List, Dict
from firebase_admin import firestore, messaging
import schemas
from crud.utils import add_timestamps

logger = logging.getLogger(__name__)


def adicionar_fcm_token(db: firestore.client, firebase_uid: str, fcm_token: str):
    """Adiciona um token FCM para um usuário."""
    try:
        user_query = db.collection('usuarios').where('firebase_uid', '==', firebase_uid).limit(1)
        user_docs = list(user_query.stream())
        
        if user_docs:
            user_ref = user_docs[0].reference
            user_data = user_docs[0].to_dict()
            
            fcm_tokens = user_data.get('fcm_tokens', [])
            if fcm_token not in fcm_tokens:
                fcm_tokens.append(fcm_token)
                user_ref.update({'fcm_tokens': fcm_tokens})
                logger.info(f"Token FCM adicionado para usuário {firebase_uid}")
            else:
                logger.info(f"Token FCM já existe para usuário {firebase_uid}")
        else:
            logger.warning(f"Usuário com firebase_uid {firebase_uid} não encontrado")
    except Exception as e:
        logger.error(f"Erro ao adicionar token FCM: {e}")


def remover_fcm_token(db: firestore.client, firebase_uid: str, fcm_token: str):
    """Remove um token FCM de um usuário."""
    try:
        user_query = db.collection('usuarios').where('firebase_uid', '==', firebase_uid).limit(1)
        user_docs = list(user_query.stream())
        
        if user_docs:
            user_ref = user_docs[0].reference
            user_data = user_docs[0].to_dict()
            
            fcm_tokens = user_data.get('fcm_tokens', [])
            if fcm_token in fcm_tokens:
                fcm_tokens.remove(fcm_token)
                user_ref.update({'fcm_tokens': fcm_tokens})
                logger.info(f"Token FCM removido para usuário {firebase_uid}")
            else:
                logger.info(f"Token FCM não encontrado para usuário {firebase_uid}")
        else:
            logger.warning(f"Usuário com firebase_uid {firebase_uid} não encontrado")
    except Exception as e:
        logger.error(f"Erro ao remover token FCM: {e}")


def _send_data_push_to_tokens(tokens: List[str], title: str, body: str, data: Dict = None) -> Dict:
    """Envia notificação push para uma lista de tokens FCM."""
    try:
        if not tokens:
            return {"success": 0, "failure": 0, "errors": []}
        
        message_data = data or {}
        message = messaging.MulticastMessage(
            notification=messaging.Notification(
                title=title,
                body=body
            ),
            data=message_data,
            tokens=tokens
        )
        
        response = messaging.send_multicast(message)
        
        success_count = response.success_count
        failure_count = response.failure_count
        errors = []
        
        for idx, result in enumerate(response.responses):
            if not result.success:
                errors.append({
                    "token": tokens[idx],
                    "error": str(result.exception)
                })
        
        logger.info(f"Push notification sent: {success_count} success, {failure_count} failures")
        
        return {
            "success": success_count,
            "failure": failure_count,
            "errors": errors
        }
        
    except Exception as e:
        logger.error(f"Erro ao enviar notificação push: {e}")
        return {"success": 0, "failure": len(tokens), "errors": [str(e)]}


def listar_notificacoes(db: firestore.client, usuario_id: str) -> List[Dict]:
    """Lista todas as notificações de um usuário."""
    notificacoes = []
    try:
        query = db.collection('notificacoes') \
                 .where('destinatario_id', '==', usuario_id) \
                 .order_by('created_at', direction=firestore.Query.DESCENDING)
        
        for doc in query.stream():
            notificacao_data = doc.to_dict()
            notificacao_data['id'] = doc.id
            notificacoes.append(notificacao_data)
        
        logger.info(f"Retornando {len(notificacoes)} notificações para usuário {usuario_id}")
        return notificacoes
    except Exception as e:
        logger.error(f"Erro ao listar notificações do usuário {usuario_id}: {e}")
        return []


def contar_notificacoes_nao_lidas(db: firestore.client, usuario_id: str) -> int:
    """Conta o número de notificações não lidas de um usuário."""
    try:
        query = db.collection('notificacoes') \
                 .where('destinatario_id', '==', usuario_id) \
                 .where('lida', '==', False)
        
        count = len(list(query.stream()))
        logger.info(f"Usuário {usuario_id} tem {count} notificações não lidas")
        return count
    except Exception as e:
        logger.error(f"Erro ao contar notificações não lidas: {e}")
        return 0


def marcar_notificacao_como_lida(db: firestore.client, usuario_id: str, notificacao_id: str) -> bool:
    """Marca uma notificação como lida."""
    try:
        notif_ref = db.collection('notificacoes').document(notificacao_id)
        notif_doc = notif_ref.get()
        
        if not notif_doc.exists:
            logger.warning(f"Notificação {notificacao_id} não encontrada")
            return False
        
        notif_data = notif_doc.to_dict()
        if notif_data.get('destinatario_id') != usuario_id:
            logger.warning(f"Usuário {usuario_id} tentou marcar notificação que não é sua")
            return False
        
        notif_ref.update({
            'lida': True,
            'data_leitura': firestore.SERVER_TIMESTAMP,
            'updated_at': firestore.SERVER_TIMESTAMP
        })
        
        logger.info(f"Notificação {notificacao_id} marcada como lida")
        return True
        
    except Exception as e:
        logger.error(f"Erro ao marcar notificação como lida: {e}")
        return False


def marcar_todas_como_lidas(db: firestore.client, usuario_id: str) -> bool:
    """Marca todas as notificações de um usuário como lidas."""
    try:
        query = db.collection('notificacoes') \
                 .where('destinatario_id', '==', usuario_id) \
                 .where('lida', '==', False)
        
        batch = db.batch()
        count = 0
        
        for doc in query.stream():
            batch.update(doc.reference, {
                'lida': True,
                'data_leitura': firestore.SERVER_TIMESTAMP,
                'updated_at': firestore.SERVER_TIMESTAMP
            })
            count += 1
        
        if count > 0:
            batch.commit()
        
        logger.info(f"Marcadas {count} notificações como lidas para usuário {usuario_id}")
        return True
        
    except Exception as e:
        logger.error(f"Erro ao marcar todas notificações como lidas: {e}")
        return False


def agendar_notificacao(db: firestore.client, notificacao_data: schemas.NotificacaoAgendadaCreate, criador_uid: str) -> Dict:
    """Agenda uma notificação para ser enviada posteriormente."""
    try:
        notif_dict = {
            'tipo': notificacao_data.tipo,
            'titulo': notificacao_data.titulo,
            'mensagem': notificacao_data.mensagem,
            'destinatario_id': notificacao_data.destinatario_id,
            'data_envio_agendada': notificacao_data.data_envio,
            'status': 'agendada',
            'criador_id': criador_uid,
            'lida': False,
            'dados_extras': notificacao_data.dados_extras or {}
        }
        
        notif_dict = add_timestamps(notif_dict, is_update=False)
        
        doc_ref = db.collection('notificacoes').document()
        doc_ref.set(notif_dict)
        notif_dict['id'] = doc_ref.id
        
        logger.info(f"Notificação agendada para {notificacao_data.destinatario_id}")
        return notif_dict
        
    except Exception as e:
        logger.error(f"Erro ao agendar notificação: {e}")
        raise


def _notificar_cliente_cancelamento(db: firestore.client, agendamento: Dict, agendamento_id: str):
    """Notifica o cliente sobre o cancelamento de um agendamento."""
    try:
        cliente_id = agendamento.get('cliente_id')
        if not cliente_id:
            return
        
        # Buscar dados do cliente
        cliente_doc = db.collection('usuarios').document(cliente_id).get()
        if not cliente_doc.exists:
            return
        
        cliente_data = cliente_doc.to_dict()
        fcm_tokens = cliente_data.get('fcm_tokens', [])
        
        if fcm_tokens:
            title = "Agendamento Cancelado"
            body = f"Seu agendamento foi cancelado. Entre em contato para reagendar."
            
            _send_data_push_to_tokens(
                tokens=fcm_tokens,
                title=title,
                body=body,
                data={
                    'tipo': 'agendamento_cancelado',
                    'agendamento_id': agendamento_id
                }
            )
        
        # Salvar notificação no banco
        notif_dict = {
            'tipo': 'agendamento_cancelado',
            'titulo': title,
            'mensagem': body,
            'destinatario_id': cliente_id,
            'lida': False,
            'dados_extras': {
                'agendamento_id': agendamento_id
            }
        }
        
        notif_dict = add_timestamps(notif_dict, is_update=False)
        
        doc_ref = db.collection('notificacoes').document()
        doc_ref.set(notif_dict)
        
        logger.info(f"Cliente {cliente_id} notificado sobre cancelamento do agendamento {agendamento_id}")
        
    except Exception as e:
        logger.error(f"Erro ao notificar cliente sobre cancelamento: {e}")