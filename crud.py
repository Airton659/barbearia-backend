# barbearia-backend/crud.py

import schemas
from datetime import datetime, date, time, timedelta
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
    negocio_id = user_data.negocio_id

    # Fluxo de Super Admin (sem negocio_id)
    is_super_admin_flow = not negocio_id
    if is_super_admin_flow:
        if not db.collection('usuarios').limit(1).get():
            user_dict = {
                "nome": user_data.nome, "email": user_data.email, "firebase_uid": user_data.firebase_uid,
                "roles": {"platform": "super_admin"}, "fcm_tokens": []
            }
            doc_ref = db.collection('usuarios').document()
            doc_ref.set(user_dict)
            user_dict['id'] = doc_ref.id
            logger.info(f"Novo usuário {user_data.email} criado como Super Admin.")
            return user_dict
        else:
            raise ValueError("Não é possível se registrar sem um negócio específico.")
    
    # Fluxo multi-tenant
    @firestore.transactional
    def transaction_sync_user(transaction):
        user_existente = buscar_usuario_por_firebase_uid(db, user_data.firebase_uid)
        
        # Se o usuário já existe
        if user_existente:
            if negocio_id not in user_existente.get("roles", {}):
                user_ref = db.collection('usuarios').document(user_existente['id'])
                transaction.update(user_ref, {f'roles.{negocio_id}': 'cliente'})
                user_existente["roles"][negocio_id] = "cliente"
                logger.info(f"Usuário existente {user_data.email} vinculado como cliente ao negócio {negocio_id}.")
            return user_existente

        # Se é um novo usuário
        negocio_doc_ref = db.collection('negocios').document(negocio_id)
        negocio_doc = negocio_doc_ref.get(transaction=transaction)

        if not negocio_doc.exists:
            raise ValueError(f"O negócio com ID '{negocio_id}' não foi encontrado.")

        negocio_data = negocio_doc.to_dict()
        has_admin = negocio_data.get('admin_uid') is not None
        role = "cliente"

        # Lógica para o primeiro admin do negócio
        if not has_admin and user_data.codigo_convite and user_data.codigo_convite == negocio_data.get('codigo_convite'):
            role = "admin"
        
        user_dict = {
            "nome": user_data.nome, "email": user_data.email, "firebase_uid": user_data.firebase_uid,
            "roles": {negocio_id: role}, "fcm_tokens": []
        }
        
        new_user_ref = db.collection('usuarios').document()
        transaction.set(new_user_ref, user_dict)
        user_dict['id'] = new_user_ref.id

        if role == "admin":
            transaction.update(negocio_doc_ref, {'admin_uid': user_data.firebase_uid})
            logger.info(f"Novo usuário {user_data.email} criado como admin do negócio {negocio_id}.")
        else:
            logger.info(f"Novo usuário {user_data.email} criado como cliente do negócio {negocio_id}.")
        
        return user_dict
    
    return transaction_sync_user(db.transaction())


def check_admin_status(db: firestore.client, negocio_id: str) -> bool:
    """Verifica se o negócio já tem um admin."""
    try:
        negocio_doc = db.collection('negocios').document(negocio_id).get()
        return negocio_doc.exists and negocio_doc.to_dict().get("admin_uid") is not None
    except Exception as e:
        logger.error(f"Erro ao verificar o status do admin para o negócio {negocio_id}: {e}")
        return False


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
# FUNÇÕES DE ADMINISTRAÇÃO DA PLATAFORMA (SUPER-ADMIN)
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
# FUNÇÕES DE ADMINISTRAÇÃO DO NEGÓCIO (ADMIN DE NEGÓCIO)
# =================================================================================

def admin_listar_usuarios_por_negocio(db: firestore.client, negocio_id: str) -> List[Dict]:
    """Lista todos os usuários (clientes e profissionais) de um negócio específico."""
    usuarios = []
    try:
        # Consulta por todos os papéis válidos dentro de um negócio
        query = db.collection('usuarios').where(f'roles.{negocio_id}', 'in', ['cliente', 'profissional', 'admin'])
        for doc in query.stream():
            usuario_data = doc.to_dict()
            usuario_data['id'] = doc.id
            usuarios.append(usuario_data)
        return usuarios
    except Exception as e:
        logger.error(f"Erro ao listar usuários para o negocio_id {negocio_id}: {e}")
        return []

def admin_listar_clientes_por_negocio(db: firestore.client, negocio_id: str) -> List[Dict]:
    """Lista todos os usuários com o papel de 'cliente' para um negócio específico."""
    clientes = []
    try:
        # No Firestore, para consultar um campo dentro de um mapa (roles), usamos a notação de ponto.
        query = db.collection('usuarios').where(f'roles.{negocio_id}', '==', 'cliente')
        for doc in query.stream():
            cliente_data = doc.to_dict()
            cliente_data['id'] = doc.id
            clientes.append(cliente_data)
        return clientes
    except Exception as e:
        logger.error(f"Erro ao listar clientes para o negocio_id {negocio_id}: {e}")
        return []

def admin_promover_cliente_para_profissional(db: firestore.client, negocio_id: str, cliente_uid: str) -> Optional[Dict]:
    """
    Promove um usuário de 'cliente' para 'profissional' e cria seu perfil profissional.
    """
    try:
        user_doc = buscar_usuario_por_firebase_uid(db, cliente_uid)
        if not user_doc:
            logger.warning(f"Tentativa de promover usuário inexistente com UID: {cliente_uid}")
            return None

        if user_doc.get("roles", {}).get(negocio_id) == 'cliente':
            # 1. Atualiza a permissão do usuário
            user_ref = db.collection('usuarios').document(user_doc['id'])
            user_ref.update({
                f'roles.{negocio_id}': 'profissional'
            })
            
            # 2. Cria o perfil profissional básico
            novo_profissional_data = schemas.ProfissionalCreate(
                negocio_id=negocio_id,
                usuario_uid=cliente_uid,
                nome=user_doc.get('nome', 'Profissional sem nome'),
                especialidades="A definir",
                ativo=True,
                fotos={}
            )
            criar_profissional(db, novo_profissional_data)
            
            logger.info(f"Usuário {user_doc['email']} promovido para profissional no negócio {negocio_id}.")
            
            # Retorna os dados atualizados do usuário
            return buscar_usuario_por_firebase_uid(db, cliente_uid)
        else:
            logger.warning(f"Usuário {user_doc.get('email')} não é um cliente deste negócio e não pode ser promovido.")
            return None
    except Exception as e:
        logger.error(f"Erro ao promover cliente {cliente_uid} para profissional: {e}")
        return None

def admin_rebaixar_profissional_para_cliente(db: firestore.client, negocio_id: str, profissional_uid: str) -> Optional[Dict]:
    """
    Rebaixa um usuário de 'profissional' para 'cliente' e desativa seu perfil profissional.
    """
    try:
        user_doc = buscar_usuario_por_firebase_uid(db, profissional_uid)
        if not user_doc:
            logger.warning(f"Tentativa de rebaixar usuário inexistente com UID: {profissional_uid}")
            return None

        if user_doc.get("roles", {}).get(negocio_id) == 'profissional':
            # 1. Atualiza a permissão do usuário
            user_ref = db.collection('usuarios').document(user_doc['id'])
            user_ref.update({
                f'roles.{negocio_id}': 'cliente'
            })
            
            # 2. Desativa o perfil profissional
            perfil_profissional = buscar_profissional_por_uid(db, negocio_id, profissional_uid)
            if perfil_profissional:
                prof_ref = db.collection('profissionais').document(perfil_profissional['id'])
                prof_ref.update({"ativo": False})

            logger.info(f"Usuário {user_doc['email']} rebaixado para cliente no negócio {negocio_id}.")
            
            # Retorna os dados atualizados do usuário
            return buscar_usuario_por_firebase_uid(db, profissional_uid)
        else:
            logger.warning(f"Usuário {user_doc.get('email')} não é um profissional deste negócio e não pode ser rebaixado.")
            return None
    except Exception as e:
        logger.error(f"Erro ao rebaixar profissional {profissional_uid}: {e}")
        return None

# =================================================================================
# FUNÇÕES DE PROFISSIONAIS E AUTOGESTÃO
# =================================================================================

def buscar_profissional_por_uid(db: firestore.client, negocio_id: str, firebase_uid: str) -> Optional[Dict]:
    """Busca um perfil de profissional com base no firebase_uid do usuário e no negocio_id."""
    try:
        query = db.collection('profissionais')\
            .where('negocio_id', '==', negocio_id)\
            .where('usuario_uid', '==', firebase_uid)\
            .limit(1)
        
        docs = list(query.stream())
        if docs:
            prof_data = docs[0].to_dict()
            prof_data['id'] = docs[0].id
            return prof_data
        return None
    except Exception as e:
        logger.error(f"Erro ao buscar profissional por UID {firebase_uid} no negócio {negocio_id}: {e}")
        return None

def atualizar_perfil_profissional(db: firestore.client, profissional_id: str, update_data: schemas.ProfissionalUpdate) -> Optional[Dict]:
    """Atualiza os dados de um perfil profissional."""
    try:
        prof_ref = db.collection('profissionais').document(profissional_id)
        update_dict = update_data.model_dump(exclude_unset=True)
        
        if not update_dict:
            return buscar_profissional_por_id(db, profissional_id)

        prof_ref.update(update_dict)
        logger.info(f"Perfil do profissional {profissional_id} atualizado.")
        
        return buscar_profissional_por_id(db, profissional_id)
    except Exception as e:
        logger.error(f"Erro ao atualizar perfil do profissional {profissional_id}: {e}")
        return None

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
        query = db.collection('profissionais').where('negocio_id', '==', negocio_id).where('ativo', '==', True)
        
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

def atualizar_servico(db: firestore.client, servico_id: str, profissional_id: str, update_data: schemas.ServicoUpdate) -> Optional[Dict]:
    """Atualiza um serviço, garantindo que ele pertence ao profissional correto."""
    try:
        servico_ref = db.collection('servicos').document(servico_id)
        servico_doc = servico_ref.get()
        
        if not servico_doc.exists or servico_doc.to_dict().get('profissional_id') != profissional_id:
            logger.warning(f"Tentativa de atualização do serviço {servico_id} por profissional não autorizado ({profissional_id}).")
            return None
            
        update_dict = update_data.model_dump(exclude_unset=True)
        if not update_dict:
            return servico_doc.to_dict()

        servico_ref.update(update_dict)
        logger.info(f"Serviço {servico_id} atualizado pelo profissional {profissional_id}.")
        
        updated_doc = servico_ref.get().to_dict()
        updated_doc['id'] = servico_id
        return updated_doc
    except Exception as e:
        logger.error(f"Erro ao atualizar serviço {servico_id}: {e}")
        return None

def deletar_servico(db: firestore.client, servico_id: str, profissional_id: str) -> bool:
    """Deleta um serviço, garantindo que ele pertence ao profissional correto."""
    try:
        servico_ref = db.collection('servicos').document(servico_id)
        servico_doc = servico_ref.get()

        if not servico_doc.exists or servico_doc.to_dict().get('profissional_id') != profissional_id:
            logger.warning(f"Tentativa de exclusão do serviço {servico_id} por profissional não autorizado ({profissional_id}).")
            return False
            
        servico_ref.delete()
        logger.info(f"Serviço {servico_id} deletado pelo profissional {profissional_id}.")
        return True
    except Exception as e:
        logger.error(f"Erro ao deletar serviço {servico_id}: {e}")
        return False

# =================================================================================
# FUNÇÕES DE DISPONIBILIDADE (HORÁRIOS, BLOQUEIOS E CÁLCULO)
# =================================================================================

def definir_horarios_trabalho(db: firestore.client, profissional_id: str, horarios: List[schemas.HorarioTrabalho]):
    """Define os horários de trabalho para um profissional, substituindo os existentes."""
    prof_ref = db.collection('profissionais').document(profissional_id)
    horarios_ref = prof_ref.collection('horarios_trabalho')
    
    batch = db.batch()
    for doc in horarios_ref.stream():
        batch.delete(doc.reference)
    batch.commit()
        
    for horario in horarios:
        horario_to_save = {
            "dia_semana": horario.dia_semana,
            "hora_inicio": horario.hora_inicio.isoformat(),
            "hora_fim": horario.hora_fim.isoformat()
        }
        horarios_ref.document(str(horario.dia_semana)).set(horario_to_save)
    
    return listar_horarios_trabalho(db, profissional_id)

def listar_horarios_trabalho(db: firestore.client, profissional_id: str) -> List[Dict]:
    """Lista os horários de trabalho de um profissional."""
    horarios = []
    horarios_ref = db.collection('profissionais').document(profissional_id).collection('horarios_trabalho')
    for doc in horarios_ref.stream():
        horario_data = doc.to_dict()
        horario_data['id'] = doc.id
        horarios.append(horario_data)
    return horarios

def criar_bloqueio(db: firestore.client, profissional_id: str, bloqueio_data: schemas.Bloqueio) -> Dict:
    """Cria um novo bloqueio na agenda de um profissional."""
    bloqueio_dict = bloqueio_data.dict()
    bloqueios_ref = db.collection('profissionais').document(profissional_id).collection('bloqueios')
    time_created, doc_ref = bloqueios_ref.add(bloqueio_dict)
    bloqueio_dict['id'] = doc_ref.id
    return bloqueio_dict

def deletar_bloqueio(db: firestore.client, profissional_id: str, bloqueio_id: str) -> bool:
    """Deleta um bloqueio da agenda de um profissional."""
    try:
        bloqueio_ref = db.collection('profissionais').document(profissional_id).collection('bloqueios').document(bloqueio_id)
        if bloqueio_ref.get().exists:
            bloqueio_ref.delete()
            return True
        return False
    except Exception as e:
        logger.error(f"Erro ao deletar bloqueio {bloqueio_id}: {e}")
        return False
        
def calcular_horarios_disponiveis(db: firestore.client, profissional_id: str, dia: date, duracao_servico_min: int = 60) -> List[time]:
    """Calcula os horários disponíveis para um profissional em um dia específico."""
    dia_semana = dia.weekday()
    
    horario_trabalho_ref = db.collection('profissionais').document(profissional_id).collection('horarios_trabalho').document(str(dia_semana))
    horario_trabalho_doc = horario_trabalho_ref.get()

    if not horario_trabalho_doc.exists:
        return [] 

    horario_trabalho = horario_trabalho_doc.to_dict()
    
    slots_disponiveis = []
    hora_inicio_str = horario_trabalho['hora_inicio']
    hora_fim_str = horario_trabalho['hora_fim']

    hora_inicio = datetime.combine(dia, time.fromisoformat(hora_inicio_str))
    hora_fim = datetime.combine(dia, time.fromisoformat(hora_fim_str))
    
    hora_atual = hora_inicio
    while hora_atual < hora_fim:
        slots_disponiveis.append(hora_atual)
        hora_atual += timedelta(minutes=duracao_servico_min)

    agendamentos_no_dia_query = db.collection('agendamentos')\
        .where('profissional_id', '==', profissional_id)\
        .where('status', '==', 'pendente')\
        .where('data_hora', '>=', datetime.combine(dia, time.min))\
        .where('data_hora', '<=', datetime.combine(dia, time.max))
        
    horarios_ocupados = {ag.to_dict()['data_hora'].replace(tzinfo=None) for ag in agendamentos_no_dia_query.stream()}
    
    bloqueios_no_dia_query = db.collection('profissionais').document(profissional_id).collection('bloqueios')\
        .where('inicio', '<=', datetime.combine(dia, time.max))\
        .where('fim', '>=', datetime.combine(dia, time.min))
    
    bloqueios = [b.to_dict() for b in bloqueios_no_dia_query.stream()]

    horarios_finais = []
    for slot in slots_disponiveis:
        if slot in horarios_ocupados:
            continue
        
        em_bloqueio = False
        for bloqueio in bloqueios:
            if bloqueio['inicio'].replace(tzinfo=None) <= slot < bloqueio['fim'].replace(tzinfo=None):
                em_bloqueio = True
                break
        
        if not em_bloqueio:
            horarios_finais.append(slot.time())
            
    return horarios_finais

# =================================================================================
# HELPER: envio FCM unitário por token (sem /batch)
# =================================================================================

def _send_data_push_to_tokens(
    db: firestore.client,
    firebase_uid_destinatario: str,
    tokens: List[str],
    data_dict: Dict[str, str],
    logger_prefix: str = ""
) -> None:
    """
    Envia mensagens data-only usando messaging.send(...) por token.
    Remove tokens inválidos (Unregistered) do usuário.
    """
    successes = 0
    failures = 0

    for t in list(tokens or []):
        try:
            messaging.send(messaging.Message(data=data_dict, token=t))
            successes += 1
        except Exception as e:
            failures += 1
            logger.error(f"{logger_prefix}Erro no token {t[:12]}…: {e}")
            msg = str(e)
            # Heurísticas comuns do Admin SDK para token inválido
            if any(s in msg for s in [
                "Unregistered",                        # Android/iOS
                "NotRegistered",                       # variação
                "requested entity was not found",      # inglês minúsculo em algumas libs
                "Requested entity was not found",      # inglês capitalizado
                "registration-token-not-registered"    # mensagem do FCM
            ]):
                try:
                    remover_fcm_token(db, firebase_uid_destinatario, t)
                    logger.info(f"{logger_prefix}Token inválido removido do usuário {firebase_uid_destinatario}.")
                except Exception as rem_err:
                    logger.error(f"{logger_prefix}Falha ao remover token inválido: {rem_err}")

    logger.info(f"{logger_prefix}Envio FCM concluído: sucesso={successes} falhas={failures}")

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


def listar_agendamentos_por_cliente(db: firestore.client, negocio_id: str, cliente_id: str) -> List[Dict]:
    """Lista os agendamentos de um cliente em um negócio específico."""
    agendamentos = []
    query = db.collection('agendamentos').where('negocio_id', '==', negocio_id).where('cliente_id', '==', cliente_id).order_by('data_hora', direction=firestore.Query.DESCENDING)
    
    for doc in query.stream():
        ag_data = doc.to_dict()
        ag_data['id'] = doc.id
        agendamentos.append(ag_data)
    
    return agendamentos

def listar_agendamentos_por_profissional(db: firestore.client, negocio_id: str, profissional_id: str) -> List[Dict]:
    """Lista os agendamentos de um profissional em um negócio específico."""
    agendamentos = []
    query = db.collection('agendamentos').where('negocio_id', '==', negocio_id).where('profissional_id', '==', profissional_id).order_by('data_hora', direction=firestore.Query.DESCENDING)
    
    for doc in query.stream():
        ag_data = doc.to_dict()
        ag_data['id'] = doc.id
        agendamentos.append(ag_data)
        
    return agendamentos

# =================================================================================
# FUNÇÕES DE FEED E INTERAÇÕES
# =================================================================================

def criar_postagem(db: firestore.client, postagem_data: schemas.PostagemCreate, profissional: Dict) -> Dict:
    """Cria uma nova postagem, desnormalizando os dados do profissional."""
    post_dict = postagem_data.dict()
    post_dict['data_postagem'] = datetime.utcnow()
    post_dict['profissional_nome'] = profissional.get('nome')
    post_dict['profissional_foto_thumbnail'] = profissional.get('fotos', {}).get('thumbnail')
    post_dict['total_curtidas'] = 0
    post_dict['total_comentarios'] = 0
    
    doc_ref = db.collection('postagens').document()
    doc_ref.set(post_dict)
    post_dict['id'] = doc_ref.id
    return post_dict

def listar_postagens_por_profissional(db: firestore.client, profissional_id: str) -> List[Dict]:
    """Lista todas as postagens de um profissional específico para seu portfólio."""
    postagens = []
    query = db.collection('postagens')\
        .where('profissional_id', '==', profissional_id)\
        .order_by('data_postagem', direction=firestore.Query.DESCENDING)
        
    for doc in query.stream():
        post_data = doc.to_dict()
        post_data['id'] = doc.id
        postagens.append(post_data)
    return postagens

def listar_feed_por_negocio(db: firestore.client, negocio_id: str, user_id: Optional[str] = None) -> List[Dict]:
    """Lista o feed de postagens de um negócio específico."""
    postagens = []
    query = db.collection('postagens')\
        .where('negocio_id', '==', negocio_id)\
        .order_by('data_postagem', direction=firestore.Query.DESCENDING)
        
    # Cache para perfis de profissionais já buscados, para evitar múltiplas leituras do mesmo perfil
    perfis_profissionais_cache = {}

    for doc in query.stream():
        post_data = doc.to_dict()
        post_data['id'] = doc.id
        
        # --- INÍCIO DA CORREÇÃO ---
        profissional_id = post_data.get('profissional_id')
        if profissional_id in perfis_profissionais_cache:
            perfil_profissional = perfis_profissionais_cache[profissional_id]
        else:
            perfil_profissional = buscar_profissional_por_id(db, profissional_id)
            perfis_profissionais_cache[profissional_id] = perfil_profissional
        
        if perfil_profissional:
            post_data['profissional_foto_thumbnail'] = perfil_profissional.get('fotos', {}).get('thumbnail')
        # --- FIM DA CORREÇÃO ---

        post_data['curtido_pelo_usuario'] = False
        if user_id:
            curtida_ref = db.collection('postagens').document(doc.id).collection('curtidas').document(user_id)
            if curtida_ref.get().exists:
                post_data['curtido_pelo_usuario'] = True
                
        postagens.append(post_data)
    return postagens

def toggle_curtida(db: firestore.client, postagem_id: str, user_id: str) -> bool:
    """Adiciona ou remove uma curtida de uma postagem."""
    post_ref = db.collection('postagens').document(postagem_id)
    curtida_ref = post_ref.collection('curtidas').document(user_id)
    
    curtida_doc = curtida_ref.get()
    
    @firestore.transactional
    def update_in_transaction(transaction, post_reference, curtida_reference, curtida_existe):
        if curtida_existe:
            transaction.delete(curtida_reference)
            transaction.update(post_reference, {
                'total_curtidas': firestore.Increment(-1)
            })
            return False  # Descurtiu
        else:
            transaction.set(curtida_reference, {'data': datetime.utcnow()})
            transaction.update(post_reference, {
                'total_curtidas': firestore.Increment(1)
            })
            return True  # Curtiu

    transaction = db.transaction()
    return update_in_transaction(transaction, post_ref, curtida_ref, curtida_doc.exists)

def criar_comentario(db: firestore.client, comentario_data: schemas.ComentarioCreate, usuario: schemas.UsuarioProfile) -> Dict:
    """Cria um novo comentário e atualiza o contador na postagem."""
    post_ref = db.collection('postagens').document(comentario_data.postagem_id)

    comentario_dict = comentario_data.dict()
    comentario_dict['data'] = datetime.utcnow()
    comentario_dict['cliente_id'] = usuario.id
    comentario_dict['cliente_nome'] = usuario.nome
    
    doc_ref = post_ref.collection('comentarios').document()
    doc_ref.set(comentario_dict)
    
    post_ref.update({'total_comentarios': firestore.Increment(1)})
    
    comentario_dict['id'] = doc_ref.id
    return comentario_dict

def listar_comentarios(db: firestore.client, postagem_id: str) -> List[Dict]:
    """Lista todos os comentários de uma postagem."""
    comentarios = []
    query = db.collection('postagens').document(postagem_id).collection('comentarios')\
        .order_by('data', direction=firestore.Query.ASCENDING)
    
    for doc in query.stream():
        comentario_data = doc.to_dict()
        comentario_data['id'] = doc.id
        comentarios.append(comentario_data)
    return comentarios

def deletar_postagem(db: firestore.client, postagem_id: str, profissional_id: str) -> bool:
    """Deleta uma postagem, garantindo que ela pertence ao profissional correto."""
    try:
        post_ref = db.collection('postagens').document(postagem_id)
        post_doc = post_ref.get()
        if not post_doc.exists or post_doc.to_dict().get('profissional_id') != profissional_id:
            logger.warning(f"Tentativa de exclusão da postagem {postagem_id} por profissional não autorizado ({profissional_id}).")
            return False
        
        # O ideal seria deletar também subcoleções como curtidas e comentários,
        # mas isso requer uma lógica mais complexa (ex: Cloud Function).
        # Por enquanto, deletamos apenas o post principal.
        post_ref.delete()
        logger.info(f"Postagem {postagem_id} deletada pelo profissional {profissional_id}.")
        return True
    except Exception as e:
        logger.error(f"Erro ao deletar postagem {postagem_id}: {e}")
        return False

def deletar_comentario(db: firestore.client, postagem_id: str, comentario_id: str, user_id: str) -> bool:
    """Deleta um comentário, garantindo que ele pertence ao usuário correto."""
    try:
        comentario_ref = db.collection('postagens').document(postagem_id).collection('comentarios').document(comentario_id)
        comentario_doc = comentario_ref.get()

        if not comentario_doc.exists or comentario_doc.to_dict().get('cliente_id') != user_id:
            logger.warning(f"Tentativa de exclusão do comentário {comentario_id} por usuário não autorizado ({user_id}).")
            return False
        
        comentario_ref.delete()
        
        # Atualiza o contador de comentários na postagem principal
        db.collection('postagens').document(postagem_id).update({
            'total_comentarios': firestore.Increment(-1)
        })
        
        logger.info(f"Comentário {comentario_id} deletado pelo usuário {user_id}.")
        return True
    except Exception as e:
        logger.error(f"Erro ao deletar comentário {comentario_id}: {e}")
        return False
        
# =================================================================================
# FUNÇÕES DE AVALIAÇÕES
# =================================================================================

def criar_avaliacao(db: firestore.client, avaliacao_data: schemas.AvaliacaoCreate, usuario: schemas.UsuarioProfile) -> Dict:
    """Cria uma nova avaliação para um profissional, desnormalizando os dados do cliente."""
    avaliacao_dict = avaliacao_data.dict()
    avaliacao_dict['data'] = datetime.utcnow()
    avaliacao_dict['cliente_id'] = usuario.id
    avaliacao_dict['cliente_nome'] = usuario.nome

    doc_ref = db.collection('avaliacoes').document()
    doc_ref.set(avaliacao_dict)
    avaliacao_dict['id'] = doc_ref.id
    
    # Opcional: recalcular a nota média do profissional aqui usando uma transação
    
    return avaliacao_dict

def listar_avaliacoes_por_profissional(db: firestore.client, profissional_id: str) -> List[Dict]:
    """Lista todas as avaliações de um profissional específico."""
    avaliacoes = []
    query = db.collection('avaliacoes')\
        .where('profissional_id', '==', profissional_id)\
        .order_by('data', direction=firestore.Query.DESCENDING)
        
    for doc in query.stream():
        avaliacao_data = doc.to_dict()
        avaliacao_data['id'] = doc.id
        avaliacoes.append(avaliacao_data)
    return avaliacoes

# =================================================================================
# FUNÇÕES DE NOTIFICAÇÕES
# =================================================================================

def listar_notificacoes(db: firestore.client, usuario_id: str) -> List[Dict]:
    """Lista o histórico de notificações de um usuário."""
    notificacoes = []
    # No Firestore, as notificações podem ser uma subcoleção dentro do documento do usuário
    query = db.collection('usuarios').document(usuario_id).collection('notificacoes')\
        .order_by('data_criacao', direction=firestore.Query.DESCENDING)
    
    for doc in query.stream():
        notificacao_data = doc.to_dict()
        notificacao_data['id'] = doc.id
        notificacoes.append(notificacao_data)
    return notificacoes

def contar_notificacoes_nao_lidas(db: firestore.client, usuario_id: str) -> int:
    """Conta o número de notificações não lidas de um usuário."""
    query = db.collection('usuarios').document(usuario_id).collection('notificacoes')\
        .where('lida', '==', False)
    
    # .get() em uma query retorna um snapshot da coleção, podemos contar os documentos
    docs = query.get()
    return len(docs)

def marcar_notificacao_como_lida(db: firestore.client, usuario_id: str, notificacao_id: str) -> bool:
    """Marca uma notificação específica de um usuário como lida."""
    try:
        notificacao_ref = db.collection('usuarios').document(usuario_id).collection('notificacoes').document(notificacao_id)
        
        # .get() em um documento para verificar se ele existe
        if notificacao_ref.get().exists:
            notificacao_ref.update({'lida': True})
            return True
        return False  # Notificação não encontrada
    except Exception as e:
        logger.error(f"Erro ao marcar notificação {notificacao_id} como lida: {e}")
        return False

def marcar_todas_como_lidas(db: firestore.client, usuario_id: str) -> bool:
    """Marca todas as notificações não lidas de um usuário como lidas."""
    try:
        notificacoes_ref = db.collection('usuarios').document(usuario_id).collection('notificacoes')
        query = notificacoes_ref.where('lida', '==', False)
        docs = query.stream()

        batch = db.batch()
        doc_count = 0
        for doc in docs:
            batch.update(doc.reference, {'lida': True})
            doc_count += 1
        
        if doc_count > 0:
            batch.commit()
            logger.info(f"{doc_count} notificações marcadas como lidas para o usuário {usuario_id}.")
        
        return True
    except Exception as e:
        logger.error(f"Erro ao marcar todas as notificações como lidas para o usuário {usuario_id}: {e}")
        return False

# =================================================================================
# HELPER: Notificação de cancelamento para o cliente
# =================================================================================

def _notificar_cliente_cancelamento(db: firestore.client, agendamento: Dict, agendamento_id: str):
    """Envia notificação para o cliente sobre o cancelamento do agendamento."""
    try:
        cliente_id = agendamento.get('cliente_id')
        if not cliente_id:
            logger.warning(f"Agendamento {agendamento_id} sem cliente_id. Não é possível notificar.")
            return

        cliente_doc_ref = db.collection('usuarios').document(cliente_id)
        cliente_doc = cliente_doc_ref.get()

        if not cliente_doc.exists:
            logger.error(f"Documento do cliente {cliente_id} não encontrado para notificação de cancelamento.")
            return
        
        cliente_data = cliente_doc.to_dict()
        cliente_data['id'] = cliente_doc.id 

        data_formatada = agendamento['data_hora'].strftime('%d/%m/%Y às %H:%M')
        mensagem_body = f"Seu agendamento com {agendamento['profissional_nome']} para {data_formatada} foi cancelado."
        
        # 1. Persistir a notificação no Firestore
        notificacao_id = f"AGENDAMENTO_CANCELADO:{agendamento_id}"
        notificacao_doc_ref = cliente_doc_ref.collection('notificacoes').document(notificacao_id)
        
        notificacao_doc_ref.set({
            "title": "Agendamento Cancelado",
            "body": mensagem_body,
            "tipo": "AGENDAMENTO_CANCELADO",
            "relacionado": { "agendamento_id": agendamento_id },
            "lida": False,
            "data_criacao": firestore.SERVER_TIMESTAMP,
            "dedupe_key": notificacao_id
        })
        logger.info(f"Notificação de cancelamento (prof.) PERSISTIDA para o cliente {cliente_id}.")

        # 2. Enviar a notificação via FCM
        fcm_tokens = cliente_data.get('fcm_tokens')
        if fcm_tokens:
            data_payload = {
                "title": "Agendamento Cancelado",
                "body": mensagem_body,
                "tipo": "AGENDAMENTO_CANCELADO",
                "agendamento_id": agendamento_id 
            }
            _send_data_push_to_tokens(
                db=db,
                firebase_uid_destinatario=cliente_data.get('firebase_uid'),
                tokens=fcm_tokens,
                data_dict=data_payload,
                logger_prefix="[Cancelamento pelo profissional] "
            )
        else:
            logger.info(f"Cliente {cliente_id} não possui tokens FCM para notificar.")

    except Exception as e:
        logger.error(f"Falha crítica na função _notificar_cliente_cancelamento para agendamento {agendamento_id}: {e}")