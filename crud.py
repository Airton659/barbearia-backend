# barbearia-backend/crud.py (Versão para Firestore Multi-Tenant)

import schemas
from datetime import datetime
from typing import Optional, List, Dict
from firebase_admin import firestore, messaging
import logging

# Setup do logger para este módulo
logger = logging.getLogger(__name__)

# =================================================================================
# FUNÇÕES DE USUÁRIOS
# =================================================================================

def buscar_usuario_por_firebase_uid(db: firestore.client, firebase_uid: str) -> Optional[Dict]:
    """Busca um usuário na coleção 'usuarios' pelo seu firebase_uid."""
    try:
        query = db.collection('usuarios').where('firebase_uid', '==', firebase_uid).limit(1)
        docs = list(query.stream())
        if docs:
            user_doc = docs[0].to_dict()
            user_doc['id'] = docs[0].id  # Adiciona o ID do documento ao dicionário
            return user_doc
        return None
    except Exception as e:
        logger.error(f"Erro ao buscar usuário por firebase_uid {firebase_uid}: {e}")
        return None

def criar_ou_atualizar_usuario(db: firestore.client, user_data: schemas.UsuarioSync) -> Dict:
    """
    Cria um novo usuário no Firestore se ele não existir, ou retorna o existente.
    Esta função é chamada pelo endpoint de sync do Firebase Auth.
    """
    # Verifica se o usuário já existe
    user_existente = buscar_usuario_por_firebase_uid(db, user_data.firebase_uid)
    if user_existente:
        return user_existente

    # Se não existe, cria um novo documento de usuário
    user_dict = {
        "nome": user_data.nome,
        "email": user_data.email,
        "firebase_uid": user_data.firebase_uid,
        "roles": {},  # Inicialmente sem roles
        "fcm_tokens": []
    }
    
    # Adiciona o novo usuário à coleção 'usuarios'
    doc_ref = db.collection('usuarios').document()
    doc_ref.set(user_dict)
    
    user_dict['id'] = doc_ref.id
    return user_dict

def adicionar_fcm_token(db: firestore.client, firebase_uid: str, fcm_token: str):
    """Adiciona um FCM token a um usuário, evitando duplicatas."""
    try:
        user_doc = buscar_usuario_por_firebase_uid(db, firebase_uid)
        if user_doc:
            doc_ref = db.collection('usuarios').document(user_doc['id'])
            # Usa a transformação de união de array do Firestore para adicionar o token de forma atômica
            doc_ref.update({
                'fcm_tokens': firestore.ArrayUnion([fcm_token])
            })
    except Exception as e:
        logger.error(f"Erro ao adicionar FCM token para o UID {firebase_uid}: {e}")

def remover_fcm_token(db: firestore.client, firebase_uid: str, fcm_token: str):
    """Remove um FCM token de um usuário."""
    try:
        user_doc = buscar_usuario_por_firebase_uid(db, firebase_uid)
        if user_doc:
            doc_ref = db.collection('usuarios').document(user_doc['id'])
            # Usa a transformação de remoção de array do Firestore
            doc_ref.update({
                'fcm_tokens': firestore.ArrayRemove([fcm_token])
            })
    except Exception as e:
        logger.error(f"Erro ao remover FCM token para o UID {firebase_uid}: {e}")


# =================================================================================
# FUNÇÕES DE PROFISSIONAIS (ANTIGOS BARBEIROS)
# =================================================================================

def criar_profissional(db: firestore.client, profissional_data: schemas.ProfissionalCreate) -> Dict:
    """Cria um novo profissional no Firestore."""
    prof_dict = profissional_data.dict()
    doc_ref = db.collection('profissionais').document()
    doc_ref.set(prof_dict)
    prof_dict['id'] = doc_ref.id
    return prof_dict

def listar_profissionais_por_negocio(db: firestore.client, negocio_id: str) -> List[Dict]:
    """Lista todos os profissionais ativos de um negócio específico."""
    profissionais = []
    try:
        query = db.collection('profissionais')\
            .where('negocio_id', '==', negocio_id)\
            .where('ativo', '==', True)
        
        for doc in query.stream():
            prof_data = doc.to_dict()
            prof_data['id'] = doc.id
            profissionais.append(prof_data)
        return profissionais
    except Exception as e:
        logger.error(f"Erro ao listar profissionais para o negocio_id {negocio_id}: {e}")
        return []

def buscar_profissional_por_id(db: firestore.client, profissional_id: str) -> Optional[Dict]:
    """Busca um profissional pelo seu ID de documento."""
    try:
        doc_ref = db.collection('profissionais').document(profissional_id)
        doc = doc_ref.get()
        if doc.exists:
            prof_data = doc.to_dict()
            prof_data['id'] = doc.id
            return prof_data
        return None
    except Exception as e:
        logger.error(f"Erro ao buscar profissional por ID {profissional_id}: {e}")
        return None

# =================================================================================
# FUNÇÕES DE SERVIÇOS
# =================================================================================

def criar_servico(db: firestore.client, servico_data: schemas.ServicoCreate) -> Dict:
    """Cria um novo serviço para um profissional."""
    servico_dict = servico_data.dict()
    doc_ref = db.collection('servicos').document()
    doc_ref.set(servico_dict)
    servico_dict['id'] = doc_ref.id
    return servico_dict

def listar_servicos_por_profissional(db: firestore.client, profissional_id: str) -> List[Dict]:
    """Lista todos os serviços de um profissional específico."""
    servicos = []
    try:
        query = db.collection('servicos').where('profissional_id', '==', profissional_id)
        for doc in query.stream():
            servico_data = doc.to_dict()
            servico_data['id'] = doc.id
            servicos.append(servico_data)
        return servicos
    except Exception as e:
        logger.error(f"Erro ao listar serviços para o profissional_id {profissional_id}: {e}")
        return []

# =================================================================================
# FUNÇÕES DE AGENDAMENTOS
# =================================================================================

def criar_agendamento(db: firestore.client, agendamento_data: schemas.AgendamentoCreate, cliente: schemas.UsuarioProfile) -> Dict:
    """Cria um novo agendamento, desnormalizando os dados necessários."""
    
    # 1. Buscar dados para desnormalização
    profissional = buscar_profissional_por_id(db, agendamento_data.profissional_id)
    servico_doc = db.collection('servicos').document(agendamento_data.servico_id).get()

    if not profissional or not servico_doc.exists:
        raise ValueError("Profissional ou serviço não encontrado.")

    servico = servico_doc.to_dict()

    # 2. Montar o documento completo do agendamento
    agendamento_dict = {
        "negocio_id": agendamento_data.negocio_id,
        "data_hora": agendamento_data.data_hora,
        "status": "pendente",
        
        # Dados do Cliente
        "cliente_id": cliente.id,
        "cliente_nome": cliente.nome,
        
        # Dados do Profissional
        "profissional_id": profissional['id'],
        "profissional_nome": profissional['nome'],
        "profissional_foto_thumbnail": profissional.get('fotos', {}).get('thumbnail'),

        # Dados do Serviço
        "servico_id": agendamento_data.servico_id,
        "servico_nome": servico['nome'],
        "servico_preco": servico['preco'],
        "servico_duracao_minutos": servico['duracao_minutos']
    }

    # 3. Salvar no Firestore
    doc_ref = db.collection('agendamentos').document()
    doc_ref.set(agendamento_dict)
    
    agendamento_dict['id'] = doc_ref.id
    return agendamento_dict


def cancelar_agendamento(db: firestore.client, agendamento_id: str, cliente_id: str) -> Optional[Dict]:
    """
    Cancela um agendamento. No Firestore, isso geralmente significa deletar o documento.
    Envia uma notificação para o profissional.
    """
    agendamento_ref = db.collection('agendamentos').document(agendamento_id)
    agendamento_doc = agendamento_ref.get()

    if not agendamento_doc.exists:
        return None # Agendamento não encontrado
    
    agendamento = agendamento_doc.to_dict()
    
    if agendamento.get('cliente_id') != cliente_id:
        return None # Usuário não autorizado
        
    # --- LÓGICA DE NOTIFICAÇÃO ---
    profissional = buscar_profissional_por_id(db, agendamento['profissional_id'])
    if profissional:
        prof_user = buscar_usuario_por_firebase_uid(db, profissional['usuario_uid'])
        if prof_user and prof_user.get('fcm_tokens'):
            data_formatada = agendamento['data_hora'].strftime('%d/%m')
            hora_formatada = agendamento['data_hora'].strftime('%H:%M')
            mensagem_body = f"O cliente {agendamento['cliente_nome']} cancelou o horário das {hora_formatada} do dia {data_formatada}."

            message = messaging.Message(
                data={
                    "title": "Agendamento Cancelado",
                    "body": mensagem_body,
                    "tipo": "AGENDAMENTO_CANCELADO_CLIENTE"
                }
            )

            for token in prof_user['fcm_tokens']:
                message.token = token
                try:
                    Messaging(message)
                    logger.info(f"Notificação de cancelamento enviada para o token do profissional: {token}")
                except Exception as e:
                    logger.error(f"Erro ao enviar notificação de cancelamento para o token {token}: {e}")

    # Deleta o documento do Firestore
    agendamento_ref.delete()
    return agendamento

# =================================================================================
# NOTA: As demais funções (Postagens, Comentários, Avaliações, etc.)
# seguiriam o mesmo padrão de reescrita. O código abaixo serve como um
# esqueleto e pode ser preenchido conforme a necessidade de cada endpoint.
# =================================================================================

def listar_agendamentos_por_cliente(db: firestore.client, negocio_id: str, cliente_id: str) -> List[Dict]:
    """Lista os agendamentos de um cliente em um negócio específico."""
    agendamentos = []
    query = db.collection('agendamentos')\
        .where('negocio_id', '==', negocio_id)\
        .where('cliente_id', '==', cliente_id)\
        .order_by('data_hora', direction=firestore.Query.DESCENDING)
    
    for doc in query.stream():
        ag_data = doc.to_dict()
        ag_data['id'] = doc.id
        agendamentos.append(ag_data)
    
    return agendamentos

def listar_agendamentos_por_profissional(db: firestore.client, negocio_id: str, profissional_id: str) -> List[Dict]:
    """Lista os agendamentos de um profissional em um negócio específico."""
    agendamentos = []
    query = db.collection('agendamentos')\
        .where('negocio_id', '==', negocio_id)\
        .where('profissional_id', '==', profissional_id)\
        .order_by('data_hora', direction=firestore.Query.DESCENDING)
    
    for doc in query.stream():
        ag_data = doc.to_dict()
        ag_data['id'] = doc.id
        agendamentos.append(ag_data)
        
    return agendamentos