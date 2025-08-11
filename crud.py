# barbearia-backend/crud.py (Versão Definitiva com Onboarding Robusto)

import schemas
from datetime import datetime
from typing import Optional, List, Dict
from firebase_admin import firestore, messaging
import logging
import secrets

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
            user_doc['id'] = docs[0].id
            return user_doc
        return None
    except Exception as e:
        logger.error(f"Erro ao buscar usuário por firebase_uid {firebase_uid}: {e}")
        return None

def criar_ou_atualizar_usuario(db: firestore.client, user_data: schemas.UsuarioSync) -> Dict:
    """
    Cria ou atualiza um usuário no Firestore.
    Esta função é a única fonte da verdade para a lógica de onboarding.
    """
    # --- FLUXO 1: CÓDIGO DE CONVITE (PRIORIDADE MÁXIMA) ---
    if user_data.codigo_convite:
        logger.info(f"Processando cadastro com código de convite: {user_data.codigo_convite}")
        negocio_query = db.collection('negocios').where('codigo_convite', '==', user_data.codigo_convite).limit(1)
        negocios = list(negocio_query.stream())
        
        if negocios:
            negocio_doc = negocios[0]
            negocio_data = negocio_doc.to_dict()
            
            # Verifica se o convite é válido e não foi utilizado
            if negocio_data.get('admin_uid') is None or negocio_data.get('admin_uid') == user_data.firebase_uid:
                negocio_id = negocio_doc.id
                user_existente = buscar_usuario_por_firebase_uid(db, user_data.firebase_uid)

                # Se o usuário já existe (ex: como cliente), ATUALIZA seu papel.
                if user_existente:
                    user_ref = db.collection('usuarios').document(user_existente['id'])
                    user_ref.update({f'roles.{negocio_id}': 'admin'})
                    logger.info(f"Usuário existente {user_data.email} PROMOVIDO a admin do negócio {negocio_id}.")
                # Se o usuário não existe, CRIA com o papel de admin.
                else:
                    user_dict = {
                        "nome": user_data.nome, "email": user_data.email, "firebase_uid": user_data.firebase_uid,
                        "roles": {negocio_id: "admin"}, "fcm_tokens": []
                    }
                    db.collection('usuarios').document().set(user_dict)
                    logger.info(f"Novo usuário {user_data.email} criado como admin do negócio {negocio_id}.")

                # Marca o convite como utilizado
                negocio_doc.reference.update({'admin_uid': user_data.firebase_uid})
                
                # Retorna os dados atualizados do usuário
                return buscar_usuario_por_firebase_uid(db, user_data.firebase_uid)
            
            else:
                logger.warning(f"Código de convite para '{negocio_data['nome']}' já foi utilizado por outro admin.")
        else:
            logger.warning(f"Código de convite '{user_data.codigo_convite}' é inválido.")

    # --- FLUXO 2: USUÁRIO EXISTENTE (SEM CÓDIGO DE CONVITE) ---
    user_existente = buscar_usuario_por_firebase_uid(db, user_data.firebase_uid)
    if user_existente:
        if user_data.negocio_id and user_data.negocio_id not in user_existente.get("roles", {}):
            doc_ref = db.collection('usuarios').document(user_existente['id'])
            doc_ref.update({f'roles.{user_data.negocio_id}': 'cliente'})
            user_existente["roles"][user_data.negocio_id] = "cliente"
        return user_existente

    # --- FLUXO 3: NOVO USUÁRIO (SEM CÓDIGO DE CONVITE) ---
    user_dict = {
        "nome": user_data.nome, "email": user_data.email, "firebase_uid": user_data.firebase_uid,
        "roles": {}, "fcm_tokens": []
    }
    
    is_super_admin_flow = not user_data.negocio_id
    if is_super_admin_flow and not db.collection('usuarios').limit(1).get():
        user_dict["roles"]["platform"] = "super_admin"
        logger.info(f"Novo usuário {user_data.email} criado como Super Admin.")
    elif user_data.negocio_id:
        user_dict["roles"][user_data.negocio_id] = "cliente"
        logger.info(f"Novo usuário {user_data.email} criado como cliente do negócio {user_data.negocio_id}.")
    
    # Usar .document().set() para consistência
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
            doc_ref.update({
                'fcm_tokens': firestore.ArrayRemove([fcm_token])
            })
    except Exception as e:
        logger.error(f"Erro ao remover FCM token para o UID {firebase_uid}: {e}")

# =================================================================================
# FUNÇÕES DE ADMINISTRAÇÃO (PARA O SUPER-ADMIN)
# =================================================================================

def admin_criar_negocio(db: firestore.client, negocio_data: schemas.NegocioCreate, owner_uid: str) -> Dict:
    """Cria um novo negócio e gera um código de convite único."""
    negocio_dict = negocio_data.dict()
    negocio_dict["owner_uid"] = owner_uid
    negocio_dict["codigo_convite"] = secrets.token_hex(4).upper()
    negocio_dict["admin_uid"] = None
    
    doc_ref = db.collection('negocios').document()
    doc_ref.set(negocio_dict)
    
    negocio_dict['id'] = doc_ref.id
    return negocio_dict

def admin_listar_negocios(db: firestore.client) -> List[Dict]:
    """Lista todos os negócios cadastrados na plataforma."""
    negocios = []
    try:
        for doc in db.collection('negocios').stream():
            negocio_data = doc.to_dict()
            negocio_data['id'] = doc.id
            negocios.append(negocio_data)
        return negocios
    except Exception as e:
        logger.error(f"Erro ao listar negócios: {e}")
        return []

# =================================================================================
# FUNÇÕES DE PROFISSIONAIS
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
    return agendamento_dict


def cancelar_agendamento(db: firestore.client, agendamento_id: str, cliente_id: str) -> Optional[Dict]:
    """
    Cancela um agendamento. No Firestore, isso geralmente significa deletar o documento.
    Envia uma notificação para o profissional.
    """
    agendamento_ref = db.collection('agendamentos').document(agendamento_id)
    agendamento_doc = agendamento_ref.get()

    if not agendamento_doc.exists:
        return None
    
    agendamento = agendamento_doc.to_dict()
    
    if agendamento.get('cliente_id') != cliente_id:
        return None
        
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

    agendamento_ref.delete()
    return agendamento

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