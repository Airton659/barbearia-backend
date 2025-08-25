# barbearia-backend/crud.py

import schemas
from datetime import datetime, date, time, timedelta
from typing import Optional, List, Dict, Union

# --- INÍCIO DA CORREÇÃO ---
from fastapi import HTTPException
# --- FIM DA CORREÇÃO ---




from pydantic import BaseModel

from firebase_admin import firestore, messaging, auth
import logging
import secrets

# --- IMPORT DO ACK: compatível com pacote ou script ---
try:
    # quando o projeto for importado como pacote (ex.: app.crud)
    from .crud_plano_ack import get_plano_ack, create_plano_ack
except Exception:
    # quando rodar como script (uvicorn main:app), sem pacote pai
    from crud_plano_ack import get_plano_ack, create_plano_ack
# ------------------------------------------------------

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
            if hasattr(user_data, 'telefone') and user_data.telefone:
                user_dict['telefone'] = user_data.telefone
            if hasattr(user_data, 'endereco') and user_data.endereco:
                user_dict['endereco'] = user_data.endereco
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
        
        negocio_doc_ref = db.collection('negocios').document(negocio_id)
        negocio_doc = negocio_doc_ref.get(transaction=transaction)

        if not negocio_doc.exists:
            raise ValueError(f"O negócio com ID '{negocio_id}' não foi encontrado.")

        negocio_data = negocio_doc.to_dict()
        has_admin = negocio_data.get('admin_uid') is not None
        
        # --- LÓGICA DE PROMOÇÃO CORRIGIDA ---
        role = "cliente"
        if not has_admin and user_data.codigo_convite and user_data.codigo_convite == negocio_data.get('codigo_convite'):
            role = "admin"
        # --- FIM DA CORREÇÃO ---
        
        # Se o usuário já existe
        if user_existente:
            user_ref = db.collection('usuarios').document(user_existente['id'])
            
            # Atualiza a role apenas se ele não tiver uma para este negócio
            if negocio_id not in user_existente.get("roles", {}):
                transaction.update(user_ref, {f'roles.{negocio_id}': role})
                user_existente["roles"][negocio_id] = role
                
                # Se foi promovido a admin, atualiza o negócio
                if role == "admin":
                    transaction.update(negocio_doc_ref, {'admin_uid': user_data.firebase_uid})
                    logger.info(f"Usuário existente {user_data.email} promovido a ADMIN do negócio {negocio_id}.")
                else:
                    logger.info(f"Usuário existente {user_data.email} vinculado como CLIENTE ao negócio {negocio_id}.")
            
            return user_existente

        # Se é um novo usuário
        user_dict = {
            "nome": user_data.nome, "email": user_data.email, "firebase_uid": user_data.firebase_uid,
            "roles": {negocio_id: role}, "fcm_tokens": []
        }
        if hasattr(user_data, 'telefone') and user_data.telefone:
            user_dict['telefone'] = user_data.telefone
        if hasattr(user_data, 'endereco') and user_data.endereco:
            user_dict['endereco'] = user_data.endereco
        
        new_user_ref = db.collection('usuarios').document()
        transaction.set(new_user_ref, user_dict)
        user_dict['id'] = new_user_ref.id

        if role == "admin":
            transaction.update(negocio_doc_ref, {'admin_uid': user_data.firebase_uid})
            logger.info(f"Novo usuário {user_data.email} criado como ADMIN do negócio {negocio_id}.")
        else:
            logger.info(f"Novo usuário {user_data.email} criado como CLIENTE do negócio {negocio_id}.")
        
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

# Em crud.py, substitua a função inteira por esta versão

# Em crud.py, substitua a função inteira por esta versão final e completa

def admin_listar_usuarios_por_negocio(db: firestore.client, negocio_id: str, status: str = 'ativo') -> List[Dict]:
    """
    Lista todos os usuários de um negócio, enriquecendo os dados com os IDs de
    vínculos de profissionais, enfermeiros e técnicos quando aplicável.
    """
    usuarios = []
    try:
        query = db.collection('usuarios').where(f'roles.{negocio_id}', 'in', ['cliente', 'profissional', 'admin', 'tecnico'])

        for doc in query.stream():
            usuario_data = doc.to_dict()
            status_no_negocio = usuario_data.get('status_por_negocio', {}).get(negocio_id, 'ativo')

            if status_no_negocio == status:
                usuario_data['id'] = doc.id
                user_role = usuario_data.get("roles", {}).get(negocio_id)

                # --- LÓGICA DE ENRIQUECIMENTO DE DADOS ---

                # 1. Para Profissionais e Admins, adiciona o profissional_id
                if user_role in ['profissional', 'admin']:
                    firebase_uid = usuario_data.get('firebase_uid')
                    if firebase_uid:
                        perfil_profissional = buscar_profissional_por_uid(db, negocio_id, firebase_uid)
                        usuario_data['profissional_id'] = perfil_profissional.get('id') if perfil_profissional else None
                    else:
                        usuario_data['profissional_id'] = None
                
                # 2. Para Clientes (Pacientes), adiciona os IDs dos profissionais vinculados
                elif user_role == 'cliente':
                    # Adiciona o ID do enfermeiro vinculado (convertido para profissional_id)
                    enfermeiro_user_id = usuario_data.get('enfermeiro_id')
                    if enfermeiro_user_id:
                        enfermeiro_doc = db.collection('usuarios').document(enfermeiro_user_id).get()
                        if enfermeiro_doc.exists:
                            firebase_uid_enfermeiro = enfermeiro_doc.to_dict().get('firebase_uid')
                            perfil_enfermeiro = buscar_profissional_por_uid(db, negocio_id, firebase_uid_enfermeiro)
                            usuario_data['enfermeiro_vinculado_id'] = perfil_enfermeiro.get('id') if perfil_enfermeiro else None
                        else:
                            usuario_data['enfermeiro_vinculado_id'] = None
                    else:
                        usuario_data['enfermeiro_vinculado_id'] = None

                    # Adiciona a lista de IDs de técnicos vinculados
                    usuario_data['tecnicos_vinculados_ids'] = usuario_data.get('tecnicos_ids', [])

                usuarios.append(usuario_data)

        return usuarios
    except Exception as e:
        logger.error(f"Erro ao listar usuários para o negocio_id {negocio_id}: {e}")
        return []

def admin_set_paciente_status(db: firestore.client, negocio_id: str, paciente_id: str, status: str, autor_uid: str) -> Optional[Dict]:
    """Define o status de um paciente ('ativo' ou 'arquivado') em um negócio."""
    if status not in ['ativo', 'arquivado']:
        raise ValueError("Status inválido. Use 'ativo' ou 'arquivado'.")

    user_ref = db.collection('usuarios').document(paciente_id)
    status_path = f'status_por_negocio.{negocio_id}'
    user_ref.update({status_path: status})

    criar_log_auditoria(
        db,
        autor_uid=autor_uid,
        negocio_id=negocio_id,
        acao=f"PACIENTE_STATUS_{status.upper()}",
        detalhes={"paciente_alvo_id": paciente_id}
    )

    logger.info(f"Status do paciente {paciente_id} definido como '{status}' no negócio {negocio_id}.")

    doc = user_ref.get()
    if doc.exists:
        data = doc.to_dict()
        data['id'] = doc.id
        return data
    return None

def admin_atualizar_role_usuario(db: firestore.client, negocio_id: str, user_id: str, novo_role: str, autor_uid: str) -> Optional[Dict]:
    """
    Atualiza a role de um usuário dentro de um negócio específico.
    Cria/desativa o perfil profissional conforme necessário.
    """
    # --- ALTERAÇÃO AQUI: Adicionando 'tecnico' à lista de roles válidas ---
    if novo_role not in ['cliente', 'profissional', 'admin', 'tecnico']:
        raise ValueError("Role inválida. As roles permitidas são 'cliente', 'profissional', 'admin' e 'tecnico'.")
    # --- FIM DA ALTERAÇÃO ---

    user_ref = db.collection('usuarios').document(user_id)
    user_doc = user_ref.get()

    if not user_doc.exists:
        logger.warning(f"Tentativa de atualizar role de usuário inexistente com ID: {user_id}")
        return None

    user_data = user_doc.to_dict()

    # Verifica se o usuário pertence ao negócio
    if negocio_id not in user_data.get("roles", {}):
        logger.warning(f"Usuário {user_id} não pertence ao negócio {negocio_id}.")
        return None

    role_antiga = user_data.get("roles", {}).get(negocio_id)

    role_path = f'roles.{negocio_id}'
    user_ref.update({role_path: novo_role})

    criar_log_auditoria(
        db,
        autor_uid=autor_uid,
        negocio_id=negocio_id,
        acao="ROLE_UPDATE",
        detalhes={"usuario_alvo_id": user_id, "role_antiga": role_antiga, "nova_role": novo_role}
    )

    # Lógica para perfil profissional
    perfil_profissional = buscar_profissional_por_uid(db, negocio_id, user_data['firebase_uid'])

    if novo_role == 'profissional' or novo_role == 'admin':
        if not perfil_profissional:
            # Cria o perfil profissional se não existir
            novo_profissional_data = schemas.ProfissionalCreate(
                negocio_id=negocio_id,
                usuario_uid=user_data['firebase_uid'],
                nome=user_data.get('nome', 'Profissional sem nome'),
                ativo=True,
                fotos={}
            )
            criar_profissional(db, novo_profissional_data)
            logger.info(f"Perfil profissional criado para o usuário {user_data['email']} no negócio {negocio_id}.")
        elif not perfil_profissional.get('ativo'):
            # Reativa o perfil se já existir e estiver inativo
            prof_ref = db.collection('profissionais').document(perfil_profissional['id'])
            prof_ref.update({"ativo": True})
            logger.info(f"Perfil profissional reativado para o usuário {user_data['email']} no negócio {negocio_id}.")

    elif novo_role == 'cliente' or novo_role == 'tecnico': # Desativa perfil se virar cliente OU tecnico
        if perfil_profissional and perfil_profissional.get('ativo'):
            # Desativa o perfil profissional se existir e estiver ativo
            prof_ref = db.collection('profissionais').document(perfil_profissional['id'])
            prof_ref.update({"ativo": False})
            logger.info(f"Perfil profissional desativado para o usuário {user_data['email']} no negócio {negocio_id}.")

    logger.info(f"Role do usuário {user_data['email']} atualizada para '{novo_role}' no negócio {negocio_id}.")

    updated_user_doc = user_ref.get()
    updated_user_data = updated_user_doc.to_dict()
    updated_user_data['id'] = updated_user_doc.id
    return updated_user_data

def admin_criar_paciente(db: firestore.client, negocio_id: str, paciente_data: schemas.PacienteCreateByAdmin) -> Dict:
    """
    (Admin ou Enfermeiro) Cria um novo usuário de paciente no Firebase Auth e o sincroniza no Firestore.
    """
    # 1. Criar usuário no Firebase Auth
    try:
        firebase_user = auth.create_user(
            email=paciente_data.email,
            password=paciente_data.password,
            display_name=paciente_data.nome,
            email_verified=False
        )
        logger.info(f"Usuário paciente criado no Firebase Auth com UID: {firebase_user.uid}")
    except auth.EmailAlreadyExistsError:
        raise ValueError(f"O e-mail {paciente_data.email} já está em uso.")
    except Exception as e:
        logger.error(f"Erro ao criar usuário paciente no Firebase Auth: {e}")
        raise

    # 2. Sincronizar o usuário no Firestore, passando todos os dados
    sync_data = schemas.UsuarioSync(
        nome=paciente_data.nome,
        email=paciente_data.email,
        firebase_uid=firebase_user.uid,
        negocio_id=negocio_id,
        telefone=paciente_data.telefone,
        endereco=paciente_data.endereco
    )

    try:
        user_profile = criar_ou_atualizar_usuario(db, sync_data)
        logger.info(f"Perfil do paciente {paciente_data.email} sincronizado no Firestore.")
        return user_profile
    except Exception as e:
        logger.error(f"Erro ao sincronizar paciente no Firestore. Tentando reverter a criação no Auth... UID: {firebase_user.uid}")
        try:
            auth.delete_user(firebase_user.uid)
            logger.info(f"Reversão bem-sucedida: usuário {firebase_user.uid} deletado do Auth.")
        except Exception as delete_e:
            logger.critical(f"FALHA CRÍTICA NA REVERSÃO: não foi possível deletar o usuário {firebase_user.uid} do Auth. {delete_e}")
        raise e

# Correção na função para garantir que o ID do documento 'usuarios' seja sempre usado
def admin_listar_clientes_por_negocio(db: firestore.client, negocio_id: str, status: str = 'ativo') -> List[Dict]:
    """Lista todos os usuários com o papel de 'cliente' para um negócio, com filtro de status."""
    clientes = []
    try:
        query = db.collection('usuarios').where(f'roles.{negocio_id}', '==', 'cliente')

        for doc in query.stream():
            cliente_data = doc.to_dict()
            status_no_negocio = cliente_data.get('status_por_negocio', {}).get(negocio_id, 'ativo')

            if status_no_negocio == status:
                cliente_data['id'] = doc.id
                
                # CORREÇÃO: Busca o ID do perfil profissional a partir do ID do usuário (enfermeiro)
                enfermeiro_user_id = cliente_data.get('enfermeiro_id')
                if enfermeiro_user_id:
                    # Busca o documento do usuário para obter o firebase_uid
                    enfermeiro_doc = db.collection('usuarios').document(enfermeiro_user_id).get()
                    if enfermeiro_doc.exists:
                        firebase_uid = enfermeiro_doc.to_dict().get('firebase_uid')
                        # Usa o firebase_uid para encontrar o perfil profissional correspondente
                        perfil_profissional = buscar_profissional_por_uid(db, negocio_id, firebase_uid)
                        if perfil_profissional:
                            cliente_data['profissional_id'] = perfil_profissional.get('id')
                        else:
                            cliente_data['profissional_id'] = None
                    else:
                         cliente_data['profissional_id'] = None
                else:
                    cliente_data['profissional_id'] = None
                
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
# FUNÇÕES DE GESTÃO CLÍNICA (MÉDICOS)
# =================================================================================

def criar_medico(db: firestore.client, medico_data: schemas.MedicoBase) -> Dict:
    """Cria um novo médico (referência) para uma clínica."""
    medico_dict = medico_data.model_dump()
    doc_ref = db.collection('medicos').document()
    doc_ref.set(medico_dict)
    medico_dict['id'] = doc_ref.id
    return medico_dict

def listar_medicos_por_negocio(db: firestore.client, negocio_id: str) -> List[Dict]:
    """Lista todos os médicos de referência de uma clínica."""
    medicos = []
    try:
        query = db.collection('medicos').where('negocio_id', '==', negocio_id)
        for doc in query.stream():
            medico_data = doc.to_dict()
            medico_data['id'] = doc.id
            medicos.append(medico_data)
        return medicos
    except Exception as e:
        logger.error(f"Erro ao listar médicos para o negocio_id {negocio_id}: {e}")
        return []

def update_medico(db: firestore.client, negocio_id: str, medico_id: str, update_data: schemas.MedicoUpdate) -> Optional[Dict]:
    """Atualiza os dados de um médico, garantindo que ele pertence ao negócio correto."""
    try:
        medico_ref = db.collection('medicos').document(medico_id)
        medico_doc = medico_ref.get()

        if not medico_doc.exists or medico_doc.to_dict().get('negocio_id') != negocio_id:
            logger.warning(f"Tentativa de atualização do médico {medico_id} por admin não autorizado ou médico inexistente.")
            return None

        update_dict = update_data.model_dump(exclude_unset=True)
        if not update_dict:
            data = medico_doc.to_dict()
            data['id'] = medico_doc.id
            return data

        medico_ref.update(update_dict)
        logger.info(f"Médico {medico_id} atualizado.")

        updated_doc = medico_ref.get().to_dict()
        updated_doc['id'] = medico_id
        return updated_doc
    except Exception as e:
        logger.error(f"Erro ao atualizar médico {medico_id}: {e}")
        return None

def delete_medico(db: firestore.client, negocio_id: str, medico_id: str) -> bool:
    """Deleta um médico, garantindo que ele pertence ao negócio correto."""
    try:
        medico_ref = db.collection('medicos').document(medico_id)
        medico_doc = medico_ref.get()

        if not medico_doc.exists or medico_doc.to_dict().get('negocio_id') != negocio_id:
            logger.warning(f"Tentativa de exclusão do médico {medico_id} por admin não autorizado ou médico inexistente.")
            return False

        medico_ref.delete()
        logger.info(f"Médico {medico_id} deletado.")
        return True
    except Exception as e:
        logger.error(f"Erro ao deletar médico {medico_id}: {e}")
        return False

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
            
            # --- INÍCIO DA CORREÇÃO ---
            # Busca o usuário correspondente para obter o e-mail
            usuario_doc = buscar_usuario_por_firebase_uid(db, prof_data.get('usuario_uid'))
            if usuario_doc:
                prof_data['email'] = usuario_doc.get('email', '') # Adiciona o e-mail ao dicionário
            else:
                prof_data['email'] = '' # Garante que o campo sempre exista
            # --- FIM DA CORREÇÃO ---

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

def agendar_notificacao(db: firestore.client, notificacao_data: schemas.NotificacaoAgendadaCreate, criador_uid: str) -> Dict:
    """
    Salva uma notificação no Firestore para ser enviada posteriormente por um worker.
    """
    agendamento_dict = notificacao_data.model_dump()
    agendamento_dict.update({
        "status": "agendada",
        "criado_em": datetime.utcnow(),
        "criado_por_uid": criador_uid,
        "tentativas_envio": 0,
        "ultimo_erro": None
    })

    doc_ref = db.collection('notificacoes_agendadas').document()
    doc_ref.set(agendamento_dict)

    agendamento_dict['id'] = doc_ref.id
    logger.info(f"Notificação agendada para paciente {notificacao_data.paciente_id} com ID: {doc_ref.id}")

    return agendamento_dict

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


# =================================================================================
# FUNÇÕES DO MÓDULO CLÍNICO
# =================================================================================

# Correção na função para garantir que o ID do documento 'usuarios' seja sempre usado
def vincular_paciente_enfermeiro(db: firestore.client, negocio_id: str, paciente_id: str, enfermeiro_id: str, autor_uid: str) -> Optional[Dict]:
    """Vincula um paciente a um enfermeiro (profissional) em uma clínica."""
    try:
        # 1. Obter o perfil profissional do enfermeiro para encontrar o UID do usuário
        perfil_enfermeiro = buscar_profissional_por_id(db, enfermeiro_id)
        if not perfil_enfermeiro:
            logger.warning(f"Tentativa de vincular a um enfermeiro inexistente com ID de profissional: {enfermeiro_id}")
            return None
            
        # 2. Encontrar o ID do documento de usuário (usuarios collection) do enfermeiro
        usuario_enfermeiro = buscar_usuario_por_firebase_uid(db, perfil_enfermeiro['usuario_uid'])
        if not usuario_enfermeiro:
             logger.warning(f"Usuário associado ao perfil profissional {enfermeiro_id} não encontrado.")
             return None
             
        # O ID a ser salvo é o ID do documento do usuário, não o ID do documento profissional.
        usuario_enfermeiro_id_para_salvar = usuario_enfermeiro['id']

        paciente_ref = db.collection('usuarios').document(paciente_id)
        # Adiciona/atualiza o campo enfermeiro_id no documento do paciente
        paciente_ref.update({
            'enfermeiro_id': usuario_enfermeiro_id_para_salvar
        })

        criar_log_auditoria(
            db,
            autor_uid=autor_uid,
            negocio_id=negocio_id,
            acao="VINCULO_PACIENTE_ENFERMEIRO",
            detalhes={"paciente_id": paciente_id, "enfermeiro_id": usuario_enfermeiro_id_para_salvar}
        )

        logger.info(f"Paciente {paciente_id} vinculado ao enfermeiro {usuario_enfermeiro_id_para_salvar} no negócio {negocio_id}.")
        doc = paciente_ref.get()
        if doc.exists:
            # Retorna o documento atualizado do paciente
            updated_doc = doc.to_dict()
            updated_doc['id'] = doc.id
            return updated_doc
        return None
    except Exception as e:
        logger.error(f"Erro ao vincular paciente {paciente_id} ao enfermeiro {enfermeiro_id}: {e}")
        return None

def desvincular_paciente_enfermeiro(db: firestore.client, negocio_id: str, paciente_id: str, autor_uid: str) -> Optional[Dict]:
    """Desvincula um paciente de um enfermeiro, removendo o campo enfermeiro_id."""
    try:
        paciente_ref = db.collection('usuarios').document(paciente_id)
        # Remove o campo enfermeiro_id do documento
        paciente_ref.update({
            'enfermeiro_id': firestore.DELETE_FIELD
        })

        criar_log_auditoria(
            db,
            autor_uid=autor_uid,
            negocio_id=negocio_id,
            acao="DESVINCULO_PACIENTE_ENFERMEIRO",
            detalhes={"paciente_id": paciente_id}
        )

        logger.info(f"Paciente {paciente_id} desvinculado de seu enfermeiro no negócio {negocio_id}.")
        doc = paciente_ref.get()
        if doc.exists:
            updated_doc = doc.to_dict()
            updated_doc['id'] = doc.id
            return updated_doc
        return None
    except Exception as e:
        logger.error(f"Erro ao desvincular paciente {paciente_id}: {e}")
        return None

# Em crud.py, substitua esta função inteira

def vincular_tecnicos_paciente(db: firestore.client, paciente_id: str, tecnicos_ids: List[str], autor_uid: str) -> Optional[Dict]:
    """
    Vincula uma lista de técnicos a um paciente.
    O campo `tecnicos_ids` no documento do paciente será substituído pela lista fornecida.
    """
    try:
        paciente_ref = db.collection('usuarios').document(paciente_id)
        
        # Validar se os IDs dos técnicos existem
        for tecnico_id in tecnicos_ids:
            tecnico_doc = db.collection('usuarios').document(tecnico_id).get()
            if not tecnico_doc.exists:
                raise ValueError(f"Técnico com ID '{tecnico_id}' não encontrado.")
            # Opcional: validar se o papel do usuário é realmente 'tecnico'
        
        paciente_ref.update({
            'tecnicos_ids': tecnicos_ids
        })

        # --- INÍCIO DA CORREÇÃO ---
        # Pegamos o documento do paciente UMA VEZ para evitar múltiplas leituras
        paciente_doc = paciente_ref.get()
        if not paciente_doc.exists:
            raise ValueError("Paciente não encontrado após a atualização.")
            
        paciente_data = paciente_doc.to_dict()
        # Convertemos as chaves (dict_keys) para uma lista antes de pegar o primeiro item
        negocio_id = list(paciente_data.get('roles', {}).keys())[0] if paciente_data.get('roles') else None
        
        if not negocio_id:
            raise ValueError("Não foi possível determinar o negocio_id do paciente para o log de auditoria.")

        criar_log_auditoria(
            db,
            autor_uid=autor_uid,
            negocio_id=negocio_id,
            acao="VINCULO_PACIENTE_TECNICO",
            detalhes={"paciente_id": paciente_id, "tecnicos_vinculados_ids": tecnicos_ids}
        )
        # --- FIM DA CORREÇÃO ---

        logger.info(f"Técnicos {tecnicos_ids} vinculados ao paciente {paciente_id}.")
        
        updated_doc = paciente_data
        updated_doc['id'] = paciente_id
        return updated_doc

    except Exception as e:
        logger.error(f"Erro ao vincular técnicos ao paciente {paciente_id}: {e}")
        raise e # Re-lança para o endpoint

def vincular_supervisor_tecnico(db: firestore.client, tecnico_id: str, supervisor_id: str, autor_uid: str) -> Optional[Dict]:
    """
    Vincula um enfermeiro supervisor a um técnico.
    """
    try:
        tecnico_ref = db.collection('usuarios').document(tecnico_id)
        tecnico_doc = tecnico_ref.get()
        if not tecnico_doc.exists:
            raise ValueError(f"Técnico com ID '{tecnico_id}' não encontrado.")
            
        supervisor_ref = db.collection('usuarios').document(supervisor_id)
        if not supervisor_ref.get().exists:
            raise ValueError(f"Supervisor com ID '{supervisor_id}' não encontrado.")
            
        # Opcional: validar se o papel do supervisor é 'profissional' ou 'admin'
        
        tecnico_ref.update({
            'supervisor_id': supervisor_id
        })
        
        criar_log_auditoria(
            db,
            autor_uid=autor_uid,
            negocio_id=list(tecnico_doc.to_dict().get('roles', {}).keys())[0], # Assumindo um único negócio
            acao="VINCULO_SUPERVISOR_TECNICO",
            detalhes={"tecnico_id": tecnico_id, "supervisor_id": supervisor_id}
        )

        logger.info(f"Supervisor {supervisor_id} vinculado ao técnico {tecnico_id}.")
        doc = tecnico_ref.get()
        if doc.exists:
            updated_doc = doc.to_dict()
            updated_doc['id'] = doc.id
            return updated_doc
        return None
    except Exception as e:
        logger.error(f"Erro ao vincular supervisor ao técnico {tecnico_id}: {e}")
        raise e # Re-lança para o endpoint

def listar_pacientes_por_profissional_ou_tecnico(db: firestore.client, negocio_id: str, usuario_id: str, role: str) -> List[Dict]:
    """
    Lista todos os pacientes vinculados a um enfermeiro ou a um técnico,
    com base no papel do usuário logado.
    """
    pacientes = []
    try:
        query = db.collection('usuarios').where(f'roles.{negocio_id}', '==', 'cliente')
        
        if role == 'profissional':
            # Se for enfermeiro, busca pacientes que têm o enfermeiro_id correspondente
            query = query.where('enfermeiro_id', '==', usuario_id)
        elif role == 'tecnico':
            # Se for técnico, busca pacientes onde o ID do técnico está na lista tecnicos_ids
            query = query.where('tecnicos_ids', 'array_contains', usuario_id)
        else:
            # Caso contrário, não retorna nada
            return []

        for doc in query.stream():
            paciente_data = doc.to_dict()
            paciente_data['id'] = doc.id
            pacientes.append(paciente_data)
        
        return pacientes
    except Exception as e:
        logger.error(f"Erro ao listar pacientes para o usuário {usuario_id} com role '{role}': {e}")
        return []

def criar_consulta(db: firestore.client, consulta_data: schemas.ConsultaCreate) -> Dict:
    """Salva uma nova consulta na subcoleção de um paciente."""
    consulta_dict = consulta_data.model_dump()
    if 'created_at' not in consulta_dict:
        try:
            consulta_dict['created_at'] = firestore.SERVER_TIMESTAMP
        except Exception:
            # fallback in case firestore.SERVER_TIMESTAMP not imported
            consulta_dict['created_at'] = datetime.utcnow()
    paciente_ref = db.collection('usuarios').document(consulta_data.paciente_id)
    doc_ref = paciente_ref.collection('consultas').document()
    doc_ref.set(consulta_dict)
    consulta_dict['id'] = doc_ref.id
    return consulta_dict

def adicionar_exame(db: firestore.client, exame_data: schemas.ExameCreate, consulta_id: str) -> Dict:
    """Salva um novo exame na subcoleção de um paciente, vinculando-o a uma consulta."""
    exame_dict = exame_data.model_dump()
    exame_dict['consulta_id'] = consulta_id
    paciente_ref = db.collection('usuarios').document(exame_data.paciente_id)
    doc_ref = paciente_ref.collection('exames').document()
    doc_ref.set(exame_dict)
    exame_dict['id'] = doc_ref.id
    return exame_dict

def prescrever_medicacao(db: firestore.client, medicacao_data: schemas.MedicacaoCreate, consulta_id: str) -> Dict:
    """Salva uma nova medicação na subcoleção de um paciente, vinculando-a a uma consulta."""
    medicacao_dict = medicacao_data.model_dump()
    medicacao_dict['data_criacao'] = datetime.utcnow()
    medicacao_dict['consulta_id'] = consulta_id
    paciente_ref = db.collection('usuarios').document(medicacao_data.paciente_id)
    doc_ref = paciente_ref.collection('medicacoes').document()
    doc_ref.set(medicacao_dict)
    medicacao_dict['id'] = doc_ref.id
    return medicacao_dict

def adicionar_item_checklist(db: firestore.client, item_data: schemas.ChecklistItemCreate, consulta_id: str) -> Dict:
    """Salva um novo item de checklist na subcoleção de um paciente, vinculando-o a uma consulta."""
    item_dict = item_data.model_dump()
    item_dict['data_criacao'] = datetime.utcnow()
    item_dict['consulta_id'] = consulta_id
    paciente_ref = db.collection('usuarios').document(item_data.paciente_id)
    doc_ref = paciente_ref.collection('checklist').document()
    doc_ref.set(item_dict)
    item_dict['id'] = doc_ref.id
    return item_dict

def criar_orientacao(db: firestore.client, orientacao_data: schemas.OrientacaoCreate, consulta_id: str) -> Dict:
    """Salva uma nova orientação na subcoleção de um paciente, vinculando-a a uma consulta."""
    orientacao_dict = orientacao_data.model_dump()
    orientacao_dict['data_criacao'] = datetime.utcnow()
    orientacao_dict['consulta_id'] = consulta_id
    paciente_ref = db.collection('usuarios').document(orientacao_data.paciente_id)
    doc_ref = paciente_ref.collection('orientacoes').document()
    doc_ref.set(orientacao_dict)
    orientacao_dict['id'] = doc_ref.id
    return orientacao_dict

# =================================================================================
# FUNÇÕES DE SUPERVISÃO
# =================================================================================

def listar_tecnicos_supervisionados_por_paciente(db: firestore.client, paciente_id: str, enfermeiro_id: str) -> List[Dict]:
    """
    Lista todos os técnicos que estão sob a supervisão do enfermeiro logado
    e que também estão vinculados ao paciente em questão.
    """
    try:
        # 1. Busca os dados do paciente para obter a lista de técnicos vinculados
        paciente_doc = db.collection('usuarios').document(paciente_id).get()
        if not paciente_doc.exists:
            logger.warning(f"Paciente com ID {paciente_id} não encontrado.")
            return []
            
        paciente_data = paciente_doc.to_dict()
        tecnicos_vinculados_ids = paciente_data.get('tecnicos_ids', [])
        
        # Se não há técnicos vinculados ao paciente, não há nada a retornar
        if not tecnicos_vinculados_ids:
            return []

        # 2. Busca todos os usuários que são técnicos e são supervisionados pelo enfermeiro
        tecnicos_supervisionados_query = db.collection('usuarios')\
            .where('roles', '==', {'tecnico': 'tecnico'}) \
            .where('supervisor_id', '==', enfermeiro_id)

        tecnicos_supervisionados = []
        for doc in tecnicos_supervisionados_query.stream():
            tecnico_data = doc.to_dict()
            tecnico_data['id'] = doc.id
            tecnicos_supervisionados.append(tecnico_data)
        
        # 3. Filtra a lista de técnicos para retornar apenas os que estão em ambas as listas
        tecnicos_finais = []
        for tecnico in tecnicos_supervisionados:
            if tecnico['id'] in tecnicos_vinculados_ids:
                tecnicos_finais.append({
                    "id": tecnico['id'],
                    "nome": tecnico.get('nome', 'Nome não disponível'),
                    "email": tecnico.get('email', 'Email não disponível')
                })
        
        return tecnicos_finais
    except Exception as e:
        logger.error(f"Erro ao listar técnicos supervisionados para o paciente {paciente_id}: {e}")
        return []

# =================================================================================
# FUNÇÕES DE LEITURA DA FICHA DO PACIENTE
        
def listar_consultas(db: firestore.client, paciente_id: str) -> List[Dict]:
    """Lista todas as consultas de um paciente."""
    consultas = []
    try:
        col = db.collection('usuarios').document(paciente_id).collection('consultas')
        query = col.order_by('created_at', direction=firestore.Query.DESCENDING).order_by('__name__', direction=firestore.Query.DESCENDING)
        for doc in query.stream():
            consulta_data = doc.to_dict()
            consulta_data['id'] = doc.id
            consultas.append(consulta_data)
        # Fallback: histórico antigo sem created_at → ordenar por ID do doc desc
        if not consultas:
            query2 = col.order_by('__name__', direction=firestore.Query.DESCENDING)
            for doc in query2.stream():
                consulta_data = doc.to_dict()
                consulta_data['id'] = doc.id
                consultas.append(consulta_data)
    except Exception as e:
        logger.error(f"Erro ao listar consultas do paciente {paciente_id}: {e}")
    return consultas

def listar_exames(db: firestore.client, paciente_id: str, consulta_id: str) -> List[Dict]:
    """Lista todos os exames de um paciente, filtrando-os pelo ID da consulta."""
    exames = []
    try:
        query = db.collection('usuarios').document(paciente_id).collection('exames').where('consulta_id', '==', consulta_id).order_by('data_exame', direction=firestore.Query.DESCENDING)
        for doc in query.stream():
            exame_data = doc.to_dict()
            exame_data['id'] = doc.id
            exames.append(exame_data)
    except Exception as e:
        logger.error(f"Erro ao listar exames do paciente {paciente_id}: {e}")
    return exames

def listar_medicacoes(db: firestore.client, paciente_id: str, consulta_id: str) -> List[Dict]:
    """Lista todas as medicações de um paciente, filtrando-as pelo ID da consulta."""
    medicacoes = []
    try:
        query = db.collection('usuarios').document(paciente_id).collection('medicacoes').where('consulta_id', '==', consulta_id).order_by('data_criacao', direction=firestore.Query.DESCENDING)
        for doc in query.stream():
            medicacao_data = doc.to_dict()
            medicacao_data['id'] = doc.id
            medicacoes.append(medicacao_data)
    except Exception as e:
        logger.error(f"Erro ao listar medicações do paciente {paciente_id}: {e}")
    return medicacoes

def listar_checklist(db: firestore.client, paciente_id: str, consulta_id: str) -> List[Dict]:
    """Lista todos os itens do checklist de um paciente, filtrando-os pelo ID da consulta."""
    checklist_itens = []
    try:
        query = db.collection('usuarios').document(paciente_id).collection('checklist').where('consulta_id', '==', consulta_id).order_by('data_criacao', direction=firestore.Query.DESCENDING)
        for doc in query.stream():
            item_data = doc.to_dict()
            item_data['id'] = doc.id
            checklist_itens.append(item_data)
    except Exception as e:
        logger.error(f"Erro ao listar checklist do paciente {paciente_id}: {e}")
    return checklist_itens

def listar_orientacoes(db: firestore.client, paciente_id: str, consulta_id: str) -> List[Dict]:
    """Lista todas as orientações de um paciente, filtrando-as pelo ID da consulta."""
    orientacoes = []
    try:
        query = db.collection('usuarios').document(paciente_id).collection('orientacoes').where('consulta_id', '==', consulta_id).order_by('data_criacao', direction=firestore.Query.DESCENDING)
        for doc in query.stream():
            orientacao_data = doc.to_dict()
            orientacao_data['id'] = doc.id
            orientacoes.append(orientacao_data)
    except Exception as e:
        logger.error(f"Erro ao listar orientações do paciente {paciente_id}: {e}")
    return orientacoes

def get_ficha_completa_paciente(db: firestore.client, paciente_id: str, consulta_id: Optional[str] = None) -> Dict:
    """
    Retorna um dicionário com todos os dados da ficha do paciente,
    filtrando para mostrar apenas o "Plano Ativo" (o mais recente).
    """
    # 1. Encontra a última consulta do paciente
    consultas = listar_consultas(db, paciente_id)
    # Se um consulta_id específico for informado (hotfix), usar direto
    if consulta_id:
        ultima_consulta_id = consulta_id
    else:
        if not consultas:
            # Se não houver consultas, não há plano ativo.
            return {
                "consultas": [],
                "exames": [],
                "medicacoes": [],
                "checklist": [],
                "orientacoes": [],
            }
        # 2. Obtém o ID da última consulta
        ultima_consulta_id = consultas[0]['id']

    ficha = {
        "consultas": consultas,
        "exames": listar_exames(db, paciente_id, consulta_id=ultima_consulta_id),
        "medicacoes": listar_medicacoes(db, paciente_id, consulta_id=ultima_consulta_id),
        "checklist": listar_checklist(db, paciente_id, consulta_id=ultima_consulta_id),
        "orientacoes": listar_orientacoes(db, paciente_id, consulta_id=ultima_consulta_id),
    }
    return ficha

# =================================================================================
# FUNÇÕES DE UPDATE/DELETE DA FICHA DO PACIENTE
# =================================================================================

def _update_subcollection_item(db: firestore.client, paciente_id: str, collection_name: str, item_id: str, update_data: BaseModel) -> Optional[Dict]:
    """Função genérica para atualizar um item em uma subcoleção do paciente."""
    try:
        item_ref = db.collection('usuarios').document(paciente_id).collection(collection_name).document(item_id)
        update_dict = update_data.model_dump(exclude_unset=True)

        if not update_dict:
            doc = item_ref.get()
            if doc.exists:
                data = doc.to_dict()
                data['id'] = doc.id
                return data
            return None

        item_ref.update(update_dict)
        doc = item_ref.get()
        if doc.exists:
            data = doc.to_dict()
            data['id'] = doc.id
            logger.info(f"Item {item_id} na coleção {collection_name} do paciente {paciente_id} atualizado.")
            return data
        return None
    except Exception as e:
        logger.error(f"Erro ao atualizar item {item_id} em {collection_name} do paciente {paciente_id}: {e}")
        return None

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

# --- Consultas ---
def update_consulta(db: firestore.client, paciente_id: str, consulta_id: str, update_data: schemas.ConsultaUpdate) -> Optional[Dict]:
    return _update_subcollection_item(db, paciente_id, "consultas", consulta_id, update_data)

def delete_consulta(db: firestore.client, paciente_id: str, consulta_id: str) -> bool:
    return _delete_subcollection_item(db, paciente_id, "consultas", consulta_id)

# --- Exames ---
def update_exame(db: firestore.client, paciente_id: str, exame_id: str, update_data: schemas.ExameUpdate) -> Optional[Dict]:
    return _update_subcollection_item(db, paciente_id, "exames", exame_id, update_data)

def delete_exame(db: firestore.client, paciente_id: str, exame_id: str) -> bool:
    return _delete_subcollection_item(db, paciente_id, "exames", exame_id)

# --- Medicações ---
def update_medicacao(db: firestore.client, paciente_id: str, medicacao_id: str, update_data: schemas.MedicacaoUpdate) -> Optional[Dict]:
    return _update_subcollection_item(db, paciente_id, "medicacoes", medicacao_id, update_data)

def delete_medicacao(db: firestore.client, paciente_id: str, medicacao_id: str) -> bool:
    return _delete_subcollection_item(db, paciente_id, "medicacoes", medicacao_id)

# --- Checklist ---
def update_checklist_item(db: firestore.client, paciente_id: str, item_id: str, update_data: schemas.ChecklistItemUpdate) -> Optional[Dict]:
    return _update_subcollection_item(db, paciente_id, "checklist", item_id, update_data)

def delete_checklist_item(db: firestore.client, paciente_id: str, item_id: str) -> bool:
    return _delete_subcollection_item(db, paciente_id, "checklist", item_id)

# --- Orientações ---
def update_orientacao(db: firestore.client, paciente_id: str, orientacao_id: str, update_data: schemas.OrientacaoUpdate) -> Optional[Dict]:
    return _update_subcollection_item(db, paciente_id, "orientacoes", orientacao_id, update_data)

def delete_orientacao(db: firestore.client, paciente_id: str, orientacao_id: str) -> bool:
    return _delete_subcollection_item(db, paciente_id, "orientacoes", orientacao_id)

# =================================================================================
# FUNÇÕES DE AUDITORIA
# =================================================================================

def criar_log_auditoria(db: firestore.client, autor_uid: str, negocio_id: str, acao: str, detalhes: Dict):
    """
    Cria um registro de log na coleção 'auditoria'.

    Args:
        autor_uid (str): Firebase UID do usuário que realizou a ação.
        negocio_id (str): ID do negócio onde a ação ocorreu.
        acao (str): Descrição da ação (ex: 'ARQUIVOU_PACIENTE').
        detalhes (Dict): Dicionário com informações contextuais (ex: {'paciente_id': 'xyz'}).
    """
    try:
        log_entry = {
            "autor_uid": autor_uid,
            "negocio_id": negocio_id,
            "acao": acao,
            "detalhes": detalhes,
            "timestamp": datetime.utcnow()
        }
        db.collection('auditoria').add(log_entry)
        logger.info(f"Log de auditoria criado para ação '{acao}' por UID {autor_uid}.")
    except Exception as e:
        # Loga o erro mas não interrompe a operação principal
        logger.error(f"Falha ao criar log de auditoria: {e}")

# --- NOVO BLOCO DE CÓDIGO AQUI ---
# =================================================================================
# FUNÇÕES DO DIÁRIO DO TÉCNICO
# =================================================================================

def criar_registro_diario(db: firestore.client, registro_data: schemas.DiarioTecnicoCreate, tecnico: schemas.UsuarioProfile) -> Dict:
    """Salva um novo registro do técnico na subcoleção de um paciente."""
    registro_dict = registro_data.model_dump()
    registro_dict.update({
        "data_ocorrencia": datetime.utcnow(),
        "tecnico_id": tecnico.id,
        "tecnico_nome": tecnico.nome,
    })
    
    paciente_ref = db.collection('usuarios').document(registro_data.paciente_id)
    doc_ref = paciente_ref.collection('diario_tecnico').document()
    doc_ref.set(registro_dict)
    
    registro_dict['id'] = doc_ref.id
    return registro_dict

def listar_registros_diario(db: firestore.client, paciente_id: str) -> List[schemas.DiarioTecnicoResponse]:
    """
    Lista todos os registros do diário de um paciente,
    retornando uma lista de objetos Pydantic para garantir a serialização correta.
    """
    registros_pydantic = []
    try:
        query = db.collection('usuarios').document(paciente_id).collection('diario_tecnico').order_by('data_ocorrencia', direction=firestore.Query.DESCENDING)
        
        tecnicos_cache = {}

        for doc in query.stream():
            registro_data = doc.to_dict()
            registro_data['id'] = doc.id
            tecnico_id = registro_data.get('tecnico_id')

            if tecnico_id:
                if tecnico_id in tecnicos_cache:
                    tecnico_perfil = tecnicos_cache[tecnico_id]
                else:
                    tecnico_doc = db.collection('usuarios').document(tecnico_id).get()
                    if tecnico_doc.exists:
                        tecnico_perfil = {
                            "id": tecnico_doc.id,
                            "nome": tecnico_doc.to_dict().get('nome'),
                            "email": tecnico_doc.to_dict().get('email')
                        }
                        tecnicos_cache[tecnico_id] = tecnico_perfil
                    else:
                        tecnico_perfil = { "id": tecnico_id, "nome": "Técnico Desconhecido", "email": "" }
                
                registro_data['tecnico'] = tecnico_perfil
            
            # Remove os campos desnormalizados antigos, que não fazem parte do schema de resposta
            registro_data.pop('tecnico_id', None)
            registro_data.pop('tecnico_nome', None)

            # Tenta validar e converter o dicionário para o modelo Pydantic
            try:
                modelo_validado = schemas.DiarioTecnicoResponse.model_validate(registro_data)
                registros_pydantic.append(modelo_validado)
            except Exception as validation_error:
                logger.error(f"Falha ao validar o registro do diário {doc.id}: {validation_error}")

    except Exception as e:
        logger.error(f"Erro ao listar o diário do paciente {paciente_id}: {e}")
    
    return registros_pydantic

def update_registro_diario(db: firestore.client, paciente_id: str, registro_id: str, update_data: schemas.DiarioTecnicoUpdate, tecnico_id: str) -> Optional[Dict]:
    """Atualiza um registro no diário do técnico, verificando a autoria."""
    try:
        item_ref = db.collection('usuarios').document(paciente_id).collection('diario_tecnico').document(registro_id)
        doc = item_ref.get()
        if not doc.exists:
            logger.warning(f"Registro do diário {registro_id} não encontrado.")
            return None
        
        if doc.to_dict().get('tecnico_id') != tecnico_id:
            logger.error(f"Técnico {tecnico_id} tentou editar registro de outro técnico.")
            raise PermissionError("Você só pode editar seus próprios registros.")

        update_dict = update_data.model_dump(exclude_unset=True)
        if not update_dict:
            data = doc.to_dict()
            data['id'] = doc.id
            return data

        item_ref.update(update_dict)
        updated_doc = item_ref.get()
        data = updated_doc.to_dict()
        data['id'] = updated_doc.id
        logger.info(f"Registro {registro_id} do paciente {paciente_id} atualizado pelo técnico {tecnico_id}.")
        return data
    except Exception as e:
        logger.error(f"Erro ao atualizar registro {registro_id} do paciente {paciente_id}: {e}")
        # Re-lança a exceção para ser tratada no endpoint
        raise e


def delete_registro_diario(db: firestore.client, paciente_id: str, registro_id: str, tecnico_id: str) -> bool:
    """Deleta um registro do diário do técnico, verificando a autoria."""
    try:
        item_ref = db.collection('usuarios').document(paciente_id).collection('diario_tecnico').document(registro_id)
        doc = item_ref.get()
        if not doc.exists:
            return False
        
        if doc.to_dict().get('tecnico_id') != tecnico_id:
            raise PermissionError("Você só pode deletar seus próprios registros.")
            
        item_ref.delete()
        logger.info(f"Registro {registro_id} do paciente {paciente_id} deletado pelo técnico {tecnico_id}.")
        return True
    except Exception as e:
        logger.error(f"Erro ao deletar registro {registro_id} do paciente {paciente_id}: {e}")
        raise e
# --- FIM DO NOVO BLOCO DE CÓDIGO ---

# --- NOVO BLOCO DE CÓDIGO AQUI ---
# =================================================================================
# FUNÇÕES DA PESQUISA DE SATISFAÇÃO
# =================================================================================

def enviar_pesquisa_satisfacao(db: firestore.client, envio_data: schemas.PesquisaEnviadaCreate) -> Dict:
    """Cria um registro de pesquisa enviada para um paciente."""
    pesquisa_dict = envio_data.model_dump()
    pesquisa_dict.update({
        "data_envio": datetime.utcnow(),
        "status": "pendente",
        "respostas": []
    })
    
    doc_ref = db.collection('pesquisas_enviadas').document()
    doc_ref.set(pesquisa_dict)
    
    pesquisa_dict['id'] = doc_ref.id
    logger.info(f"Pesquisa {envio_data.modelo_pesquisa_id} enviada para o paciente {envio_data.paciente_id}.")
    
    # Aqui, você pode adicionar a lógica para enviar uma notificação FCM para o paciente
    
    return pesquisa_dict

def submeter_respostas_pesquisa(db: firestore.client, pesquisa_enviada_id: str, respostas_data: schemas.SubmeterPesquisaRequest, paciente_id: str) -> Optional[Dict]:
    """Salva as respostas de um paciente para uma pesquisa e atualiza o status."""
    pesquisa_ref = db.collection('pesquisas_enviadas').document(pesquisa_enviada_id)
    pesquisa_doc = pesquisa_ref.get()

    if not pesquisa_doc.exists or pesquisa_doc.to_dict().get('paciente_id') != paciente_id:
        logger.error(f"Paciente {paciente_id} tentou responder pesquisa {pesquisa_enviada_id} que não lhe pertence ou não existe.")
        return None

    if pesquisa_doc.to_dict().get('status') == 'respondida':
        logger.warning(f"Paciente {paciente_id} tentou responder a pesquisa {pesquisa_enviada_id} novamente.")
        # Retorna o documento como está, sem erro
        data = pesquisa_doc.to_dict()
        data['id'] = pesquisa_doc.id
        return data

    update_dict = {
        "status": "respondida",
        "data_resposta": datetime.utcnow(),
        "respostas": [item.model_dump() for item in respostas_data.respostas]
    }
    
    pesquisa_ref.update(update_dict)
    
    updated_doc = pesquisa_ref.get()
    data = updated_doc.to_dict()
    data['id'] = updated_doc.id
    return data

def listar_pesquisas_por_paciente(db: firestore.client, negocio_id: str, paciente_id: str) -> List[Dict]:
    """Lista todas as pesquisas (pendentes e respondidas) de um paciente."""
    pesquisas = []
    try:
        query = db.collection('pesquisas_enviadas')\
            .where('negocio_id', '==', negocio_id)\
            .where('paciente_id', '==', paciente_id)\
            .order_by('data_envio', direction=firestore.Query.DESCENDING)
        
        for doc in query.stream():
            data = doc.to_dict()
            data['id'] = doc.id
            pesquisas.append(data)
    except Exception as e:
        logger.error(f"Erro ao listar pesquisas do paciente {paciente_id}: {e}")
    return pesquisas

def listar_resultados_pesquisas(db: firestore.client, negocio_id: str, modelo_pesquisa_id: Optional[str] = None) -> List[Dict]:
    """(Admin) Lista todos os resultados das pesquisas de satisfação respondidas."""
    resultados = []
    try:
        query = db.collection('pesquisas_enviadas')\
            .where('negocio_id', '==', negocio_id)\
            .where('status', '==', 'respondida')

        if modelo_pesquisa_id:
            query = query.where('modelo_pesquisa_id', '==', modelo_pesquisa_id)
        
        # Como não podemos usar '!=' ou 'not-in', a ordenação ajuda a agrupar
        query = query.order_by('data_resposta', direction=firestore.Query.DESCENDING)

        for doc in query.stream():
            data = doc.to_dict()
            data['id'] = doc.id
            resultados.append(data)
    except Exception as e:
        logger.error(f"Erro ao listar resultados de pesquisas para o negócio {negocio_id}: {e}")
    return resultados
# --- FIM DO NOVO BLOCO DE CÓDIGO ---

# --- NOVAS FUNÇÕES AQUI ---
# =================================================================================
# FUNÇÕES DE PLANO DE CUIDADO E AUDITORIA
# =================================================================================

def registrar_confirmacao_leitura_plano(db: firestore.client, paciente_id: str, confirmacao: schemas.ConfirmacaoLeituraCreate) -> Dict:
    """Registra a confirmação de leitura do plano de cuidado de um paciente por um técnico."""
    confirmacao_dict = confirmacao.model_dump()
    confirmacao_dict.update({
        "paciente_id": paciente_id,
        "data_confirmacao": datetime.utcnow()
    })
    
    # Salva a confirmação em uma subcoleção do paciente, para facilitar a consulta
    paciente_ref = db.collection('usuarios').document(paciente_id)
    doc_ref = paciente_ref.collection('confirmacoes_leitura').document()
    doc_ref.set(confirmacao_dict)

    confirmacao_dict['id'] = doc_ref.id
    return confirmacao_dict

def verificar_leitura_plano_do_dia(db: firestore.client, paciente_id: str, tecnico_id: str, data: date) -> bool:
    """Verifica se a leitura do plano de cuidado já foi confirmada pelo técnico em um dia específico."""
    data_inicio_dia = datetime.combine(data, datetime.min.time())
    data_fim_dia = datetime.combine(data, datetime.max.time())
    
    query = db.collection('usuarios').document(paciente_id).collection('confirmacoes_leitura')\
        .where('usuario_id', '==', tecnico_id)\
        .where('data_confirmacao', '>=', data_inicio_dia)\
        .where('data_confirmacao', '<=', data_fim_dia)\
        .limit(1)
        
    return len(list(query.stream())) > 0

# =================================================================================
# FUNÇÕES DO DIÁRIO DE ACOMPANHAMENTO ESTRUTURADO
# =================================================================================

def adicionar_registro_diario(db: firestore.client, paciente_id: str, registro: schemas.RegistroDiarioCreate, tecnico_id: str) -> Dict:
    """Adiciona um novo registro estruturado ao diário de acompanhamento."""
    registro_dict = registro.model_dump()
    registro_dict.update({
        "paciente_id": paciente_id,
        "tecnico_id": tecnico_id,
        "data_registro": datetime.utcnow()
    })

    paciente_ref = db.collection('usuarios').document(paciente_id)
    doc_ref = paciente_ref.collection('registros_diarios_estruturados').document()
    doc_ref.set(registro_dict)
    
    registro_dict['id'] = doc_ref.id
    return registro_dict
    
# =================================================================================
# FUNÇÕES DO CHECKLIST DIÁRIO
# =================================================================================



def listar_checklist_diario(db: firestore.client, paciente_id: str, dia: date, negocio_id: str) -> List[Dict]:
    """Busca os itens do checklist do *dia* para um paciente.

    Lê da coleção ``usuarios/{paciente_id}/checklist`` filtrando:
      - paciente_id == <paciente_id>
      - negocio_id == <negocio_id>
      - data_criacao >= {dia} 00:00:00  and  < {dia}+1 00:00:00
    Retorna uma lista no formato esperado pelo schema ``ChecklistItemDiarioResponse``:
      ``[{id, descricao, concluido}]``.
    """
    try:
        # Faixa de horário do dia em UTC (naive -> interpretado como UTC pelo client)
        start_dt = datetime.combine(dia, time(0, 0, 0))
        end_dt = start_dt + timedelta(days=1)

        col_ref = db.collection('usuarios').document(paciente_id).collection('checklist')

        query = (
            col_ref
            .where('paciente_id', '==', paciente_id)
            .where('negocio_id', '==', negocio_id)
            .where('data_criacao', '>=', start_dt)
            .where('data_criacao', '<', end_dt)
            .order_by('data_criacao')
        )

        docs = list(query.stream())

        itens: List[Dict] = []
        for doc in docs:
            d = doc.to_dict() or {}
            itens.append({
                'id': doc.id,
                'descricao': d.get('descricao_item', d.get('descricao', '')),
                'concluido': bool(d.get('concluido', False)),
            })

        return itens
    except Exception as e:
        logger.error(f"Erro ao listar checklist diário (paciente={paciente_id}, dia={dia}, negocio_id={negocio_id}): {e}")
        raise

def atualizar_item_checklist_diario(db: firestore.client, paciente_id: str, data: date, item_id: str, update_data: schemas.ChecklistItemDiarioUpdate) -> Optional[Dict]:
    """
    Atualiza o status de um item do checklist diário.
    """
    data_str = data.isoformat()
    checklist_doc_ref = db.collection('usuarios').document(paciente_id).collection('checklists_diarios').document(data_str)
    
    # Transação para garantir a atomicidade da atualização do array
    @firestore.transactional
    def update_in_transaction(transaction, doc_ref):
        snapshot = doc_ref.get(transaction=transaction)
        if not snapshot.exists:
            raise ValueError("Checklist diário não encontrado para este dia.")

        checklist = snapshot.to_dict()
        itens = checklist.get('itens', [])
        
        item_encontrado = None
        for item in itens:
            if item.get('id') == item_id:
                item_encontrado = item
                break
        
        if not item_encontrado:
            raise ValueError(f"Item do checklist com ID '{item_id}' não encontrado.")
            
        item_encontrado['concluido'] = update_data.concluido
        
        transaction.update(doc_ref, {'itens': itens})
        return item_encontrado

    try:
        updated_item = update_in_transaction(db.transaction(), checklist_doc_ref)
        return updated_item
    except ValueError as e:
        logger.error(f"Erro ao atualizar item do checklist {item_id}: {e}")
        return None
    
# Em crud.py, adicione este bloco no final do arquivo

# =================================================================================
# FUNÇÕES DO FLUXO DO TÉCNICO (BASEADO NO PDF ESTRATÉGIA)
# =================================================================================

def registrar_confirmacao_leitura_plano(db: firestore.client, paciente_id: str, confirmacao: schemas.ConfirmacaoLeituraCreate) -> Dict:
    """Cria o registro de auditoria da confirmação de leitura."""
    confirmacao_dict = confirmacao.model_dump()
    confirmacao_dict.update({
        "paciente_id": paciente_id,
        "data_confirmacao": datetime.utcnow()
    })
    paciente_ref = db.collection('usuarios').document(paciente_id)
    doc_ref = paciente_ref.collection('confirmacoes_leitura').document()
    doc_ref.set(confirmacao_dict)
    confirmacao_dict['id'] = doc_ref.id
    return confirmacao_dict

def verificar_leitura_plano_do_dia(db: firestore.client, paciente_id: str, tecnico_id: str, data: date) -> bool:
    """Verifica se a confirmação de leitura já foi feita para bloquear/liberar as funções."""
    data_inicio_dia = datetime.combine(data, datetime.min.time())
    data_fim_dia = datetime.combine(data, datetime.max.time())
    query = db.collection('usuarios').document(paciente_id).collection('confirmacoes_leitura')\
        .where('usuario_id', '==', tecnico_id)\
        .where('data_confirmacao', '>=', data_inicio_dia)\
        .where('data_confirmacao', '<=', data_fim_dia).limit(1)
    return len(list(query.stream())) > 0

def listar_checklist_diario_com_replicacao(db: firestore.client, paciente_id: str, dia: date, negocio_id: str) -> List[Dict]:
    """Busca o checklist do dia. Se não existir, replica o do dia anterior, como definido na estratégia."""
    start_dt = datetime.combine(dia, time.min)
    end_dt = datetime.combine(dia, time.max)
    col_ref = db.collection('usuarios').document(paciente_id).collection('checklist')
    query = col_ref.where('negocio_id', '==', negocio_id).where('data_criacao', '>=', start_dt).where('data_criacao', '<=', end_dt)
    docs_hoje = list(query.stream())

    if docs_hoje:
        return [{'id': doc.id, 'descricao': doc.to_dict().get('descricao_item', doc.to_dict().get('descricao', '')), 'concluido': doc.to_dict().get('concluido', False)} for doc in docs_hoje]

    query_anterior = col_ref.where('negocio_id', '==', negocio_id).where('data_criacao', '<', start_dt).order_by('data_criacao', direction=firestore.Query.DESCENDING).limit(1)
    docs_anteriores = list(query_anterior.stream())
    if not docs_anteriores: return []

    ultimo_item_data = docs_anteriores[0].to_dict()['data_criacao'].date()
    start_anterior = datetime.combine(ultimo_item_data, time.min)
    end_anterior = datetime.combine(ultimo_item_data, time.max)
    query_para_replicar = col_ref.where('negocio_id', '==', negocio_id).where('data_criacao', '>=', start_anterior).where('data_criacao', '<=', end_anterior)
    docs_para_replicar = list(query_para_replicar.stream())

    batch = db.batch()
    novos_itens = []
    for doc in docs_para_replicar:
        dados_antigos = doc.to_dict()
        novos_dados = {
            "paciente_id": paciente_id, "negocio_id": negocio_id,
            "descricao_item": dados_antigos.get("descricao_item", dados_antigos.get("descricao", "")), "concluido": False,
            "data_criacao": datetime.combine(dia, datetime.utcnow().time()),
            "consulta_id": dados_antigos.get("consulta_id")
        }
        novo_doc_ref = col_ref.document()
        batch.set(novo_doc_ref, novos_dados)
        novos_itens.append({'id': novo_doc_ref.id, 'descricao': novos_dados['descricao_item'], 'concluido': novos_dados['concluido']})
    batch.commit()
    logger.info(f"Replicados {len(novos_itens)} itens de checklist para o paciente {paciente_id} no dia {dia.isoformat()}.")
    return novos_itens

def atualizar_item_checklist_diario(db: firestore.client, paciente_id: str, item_id: str, update_data: schemas.ChecklistItemDiarioUpdate) -> Optional[Dict]:
    """Permite ao técnico marcar os itens ao longo do dia."""
    item_ref = db.collection('usuarios').document(paciente_id).collection('checklist').document(item_id)
    if not item_ref.get().exists: return None
    item_ref.update(update_data.model_dump())
    updated_doc = item_ref.get().to_dict()
    return {'id': item_id, 'descricao': updated_doc.get('descricao_item', ''), 'concluido': updated_doc.get('concluido', False)}

# =================================================================================
# FUNÇÕES DE REGISTROS DIÁRIOS ESTRUTURADOS
# =================================================================================

def criar_registro_diario_estruturado(db: firestore.client, registro_data: schemas.RegistroDiarioCreate, tecnico_id: str) -> Dict:
    """
    Adiciona um novo registro estruturado ao diário de acompanhamento de um paciente.
    Agora valida que 'conteudo' é compatível com o 'tipo' informado; caso contrário, retorna 422.
    """
    # Revalida o conteudo de acordo com o tipo escolhido (para evitar documentos corrompidos)
    try:
        tipo = registro_data.tipo
        bruto = registro_data.conteudo if isinstance(registro_data.conteudo, dict) else registro_data.conteudo.model_dump()
        if tipo == 'sinais_vitais':
            conteudo_ok = schemas.SinaisVitaisConteudo.model_validate(bruto)
        elif tipo == 'medicacao':
            conteudo_ok = schemas.MedicacaoConteudo.model_validate(bruto)
        elif tipo == 'atividade':
            conteudo_ok = schemas.AtividadeConteudo.model_validate(bruto)
        elif tipo == 'anotacao':
            conteudo_ok = schemas.AnotacaoConteudo.model_validate(bruto)
        elif tipo == 'intercorrencia':
            conteudo_ok = schemas.IntercorrenciaConteudo.model_validate(bruto)
        else:
            raise ValueError(f"Tipo de registro desconhecido: {tipo}")
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Conteúdo incompatível com o tipo '{registro_data.tipo}': {e}")

    # Monta o dicionário para salvar no Firestore
    registro_dict_para_salvar = {
        "negocio_id": registro_data.negocio_id,
        "paciente_id": registro_data.paciente_id,
        "tipo": tipo,
        "conteudo": conteudo_ok.model_dump(),
        "tecnico_id": tecnico_id,
        "data_registro": datetime.utcnow(),
    }

    # Salva o documento no banco de dados
    paciente_ref = db.collection('usuarios').document(registro_data.paciente_id)
    doc_ref = paciente_ref.collection('registros_diarios_estruturados').document()
    doc_ref.set(registro_dict_para_salvar)

    # Monta o técnico (objeto reduzido)
    tecnico_doc = db.collection('usuarios').document(tecnico_id).get()
    if tecnico_doc.exists:
        tdat = tecnico_doc.to_dict() or {}
        tecnico_perfil = {
            "id": tecnico_doc.id,
            "nome": tdat.get('nome', 'Nome não disponível'),
            "email": tdat.get('email', 'Email não disponível'),
        }
    else:
        tecnico_perfil = {"id": tecnico_id, "nome": "Técnico Desconhecido", "email": ""}

    resposta_dict = registro_dict_para_salvar.copy()
    resposta_dict['id'] = doc_ref.id
    resposta_dict['tecnico'] = tecnico_perfil
    return resposta_dict

def listar_registros_diario_estruturado(
    db: firestore.client,
    paciente_id: str,
    data: Optional[date] = None,
    tipo: Optional[str] = None
) -> List[schemas.RegistroDiarioResponse]:
    """
    Lista os registros diários estruturados de um paciente.
    Corrige os erros de validação sem adulterar o 'tipo' salvo no documento.
    Se o 'conteudo' não bater com o tipo, preenche campos obrigatórios com
    valores vazios/sensatos para não quebrar o app e manter os CAMPOS do tipo original.
    """
    registros_pydantic: List[schemas.RegistroDiarioResponse] = []
    try:
        coll_ref = db.collection('usuarios').document(paciente_id).collection('registros_diarios_estruturados')
        # ordena por data (mais recentes primeiro)
        try:
            query = coll_ref.order_by('data_registro', direction=firestore.Query.DESCENDING)
        except Exception:
            # alguns emuladores/bancos não aceitam order_by antes do where
            query = coll_ref

        # filtro por tipo se enviado
        if tipo:
            query = query.where('tipo', '==', tipo)

        # filtro por data (dentro do dia em UTC)
        if data:
            inicio = datetime.combine(data, time.min)
            fim = datetime.combine(data, time.max)
            query = query.where('data_registro', '>=', inicio).where('data_registro', '<=', fim)

        docs = list(query.stream())
        tecnicos_cache: Dict[str, Dict] = {}

        for doc in docs:
            d = doc.to_dict() or {}
            d['id'] = doc.id

            tipo_salvo = d.get('tipo')
            conteudo_bruto = d.get('conteudo', {}) or {}

            # --- valida o conteudo respeitando o TIPO SALVO ---
            def _coerce_for_tipo(tipo_salvo: str, bruto: Dict) -> BaseModel:
                try:
                    if tipo_salvo == 'sinais_vitais':
                        return schemas.SinaisVitaisConteudo.model_validate(bruto)
                    elif tipo_salvo == 'medicacao':
                        try:
                            return schemas.MedicacaoConteudo.model_validate(bruto)
                        except Exception:
                            # Monta mínimo viável preservando o que der
                            return schemas.MedicacaoConteudo(
                                nome=str(bruto.get('nome') or ''),
                                dose=str(bruto.get('dose') or ''),
                                status=str(bruto.get('status') or 'pendente'),
                                observacoes=bruto.get('observacoes') or bruto.get('descricao')
                            )
                    elif tipo_salvo == 'atividade':
                        try:
                            return schemas.AtividadeConteudo.model_validate(bruto)
                        except Exception:
                            return schemas.AtividadeConteudo(
                                nome_atividade=bruto.get('nome_atividade'),
                                duracao_minutos=bruto.get('duracao_minutos'),
                                descricao=bruto.get('descricao')
                            )
                    elif tipo_salvo == 'anotacao':
                        try:
                            return schemas.AnotacaoConteudo.model_validate(bruto)
                        except Exception:
                            return schemas.AnotacaoConteudo(
                                descricao=str(bruto.get('descricao') or '')
                            )
                    elif tipo_salvo == 'intercorrencia':
                        try:
                            return schemas.IntercorrenciaConteudo.model_validate(bruto)
                        except Exception:
                            return schemas.IntercorrenciaConteudo(
                                tipo=str(bruto.get('tipo') or 'indefinido'),
                                descricao=str(bruto.get('descricao') or ''),
                                comunicado_enfermeiro=bool(bruto.get('comunicado_enfermeiro') or False)
                            )
                    else:
                        # tipo desconhecido -> devolve como sinais vitais (campos livres) para não quebrar
                        return schemas.SinaisVitaisConteudo.model_validate(bruto)
                except Exception:
                    # pior caso: sempre retorna um objeto válido de sinais vitais
                    return schemas.SinaisVitaisConteudo()

            conteudo_validado = _coerce_for_tipo(tipo_salvo, conteudo_bruto)

            # monta o objeto 'tecnico'
            tecnico_id = d.pop('tecnico_id', None)
            tecnico_perfil = None
            if tecnico_id:
                if tecnico_id in tecnicos_cache:
                    tecnico_perfil = tecnicos_cache[tecnico_id]
                else:
                    tdoc = db.collection('usuarios').document(tecnico_id).get()
                    if tdoc.exists:
                        tdat = tdoc.to_dict() or {}
                        tecnico_perfil = {
                            'id': tdoc.id,
                            'nome': tdat.get('nome', 'Nome não disponível'),
                            'email': tdat.get('email', 'Email não disponível'),
                        }
                    else:
                        tecnico_perfil = {'id': tecnico_id, 'nome': 'Técnico Desconhecido', 'email': ''}
                    tecnicos_cache[tecnico_id] = tecnico_perfil

            registro_data = {
                'id': d['id'],
                'negocio_id': d.get('negocio_id'),
                'paciente_id': d.get('paciente_id'),
                'tecnico': tecnico_perfil or {'id': '', 'nome': '', 'email': ''},
                'data_registro': d.get('data_registro'),
                'tipo': tipo_salvo or 'anotacao',
                'conteudo': conteudo_validado
            }

            try:
                registros_pydantic.append(schemas.RegistroDiarioResponse.model_validate(registro_data))
            except Exception as e:
                logger.error(f"Falha ao montar o modelo de resposta final para o registro {doc.id}: {e}")

    except Exception as e:
        logger.error(f"Erro ao listar registros estruturados para o paciente {paciente_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao consultar o banco de dados: {e}")
    return registros_pydantic

def atualizar_registro_diario_estruturado(
    db: firestore.client, 
    paciente_id: str, 
    registro_id: str, 
    update_data: schemas.RegistroDiarioCreate,
    tecnico_id: str
) -> Optional[Dict]:
    """Atualiza um registro estruturado, validando a autoria."""
    try:
        item_ref = db.collection('usuarios').document(paciente_id).collection('registros_diarios_estruturados').document(registro_id)
        doc = item_ref.get()
        if not doc.exists:
            logger.warning(f"Registro estruturado {registro_id} não encontrado.")
            return None
        
        if doc.to_dict().get('tecnico_id') != tecnico_id:
            raise PermissionError("Você só pode editar seus próprios registros.")
            
        update_dict = update_data.model_dump(exclude_unset=True)
        if not update_dict:
            data = doc.to_dict()
            data['id'] = doc.id
            return data
            
        item_ref.update(update_dict)
        updated_doc = item_ref.get()
        data = updated_doc.to_dict()
        data['id'] = updated_doc.id
        logger.info(f"Registro estruturado {registro_id} do paciente {paciente_id} atualizado pelo técnico {tecnico_id}.")
        return data
    except Exception as e:
        logger.error(f"Erro ao atualizar registro estruturado {registro_id} do paciente {paciente_id}: {e}")
        raise e

def deletar_registro_diario_estruturado(
    db: firestore.client,
    paciente_id: str,
    registro_id: str,
    tecnico_id: str
) -> bool:
    """Deleta um registro estruturado, validando a autoria."""
    try:
        item_ref = db.collection('usuarios').document(paciente_id).collection('registros_diarios_estruturados').document(registro_id)
        doc = item_ref.get()
        if not doc.exists:
            return False
            
        if doc.to_dict().get('tecnico_id') != tecnico_id:
            raise PermissionError("Você só pode deletar seus próprios registros.")
            
        item_ref.delete()
        logger.info(f"Registro estruturado {registro_id} do paciente {paciente_id} deletado pelo técnico {tecnico_id}.")
        return True
    except Exception as e:
        logger.error(f"Erro ao deletar registro estruturado {registro_id} do paciente {paciente_id}: {e}")
        raise e

# --- FIM DAS NOVAS FUNÇÕES ---