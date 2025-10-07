# barbearia-backend/crud.py

import schemas
from datetime import datetime, date, time, timedelta, timezone
from typing import Optional, List, Dict, Union
from crypto_utils import encrypt_data, decrypt_data


# --- INÍCIO DA CORREÇÃO ---
from fastapi import HTTPException
# --- FIM DA CORREÇÃO ---




from pydantic import BaseModel

from firebase_admin import firestore, messaging, auth
import logging
import secrets
from firebase_admin.firestore import transactional

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
    """Busca um usuário na coleção 'usuarios' pelo seu firebase_uid e descriptografa os dados sensíveis."""
    try:
        logger.info(f"🔍 BUSCAR_USUARIO DEBUG - Procurando firebase_uid: {firebase_uid}")
        query = db.collection('usuarios').where('firebase_uid', '==', firebase_uid).limit(1)
        docs = list(query.stream())
        logger.info(f"🔍 BUSCAR_USUARIO DEBUG - Documentos encontrados: {len(docs)}")
        if docs:
            user_doc = docs[0].to_dict()
            user_doc['id'] = docs[0].id
            logger.info(f"🔍 BUSCAR_USUARIO DEBUG - Usuário encontrado ID: {user_doc['id']}")
            logger.info(f"🔍 BUSCAR_USUARIO DEBUG - Dados brutos: nome_len={len(user_doc.get('nome', ''))}, telefone={user_doc.get('telefone', 'None')}, email={user_doc.get('email', 'None')}")
            logger.info(f"🔍 BUSCAR_USUARIO DEBUG - Campos de imagem: profile_image_url={user_doc.get('profile_image_url', 'None')}, profile_image={user_doc.get('profile_image', 'None')}")

            # Descriptografa os campos com tratamento individual de erros
            if 'nome' in user_doc:
                try:
                    user_doc['nome'] = decrypt_data(user_doc['nome'])
                    logger.info(f"✅ BUSCAR_USUARIO DEBUG - Nome descriptografado com sucesso")
                except Exception as e:
                    logger.error(f"❌ BUSCAR_USUARIO DEBUG - Erro ao descriptografar NOME: {e}")
                    user_doc['nome'] = '[Erro na descriptografia do nome]'
            
            if 'telefone' in user_doc and user_doc['telefone']:
                try:
                    user_doc['telefone'] = decrypt_data(user_doc['telefone'])
                    logger.info(f"✅ BUSCAR_USUARIO DEBUG - Telefone descriptografado com sucesso")
                except Exception as e:
                    logger.error(f"❌ BUSCAR_USUARIO DEBUG - Erro ao descriptografar TELEFONE: {e}")
                    user_doc['telefone'] = None
            
            if 'endereco' in user_doc and user_doc['endereco']:
                try:
                    endereco_descriptografado = {}
                    for k, v in user_doc['endereco'].items():
                        if v and isinstance(v, str) and v.strip():
                            try:
                                endereco_descriptografado[k] = decrypt_data(v)
                            except Exception as field_error:
                                logger.warning(f"⚠️ BUSCAR_USUARIO DEBUG - Erro ao descriptografar campo '{k}' do endereço: {field_error}")
                                endereco_descriptografado[k] = None
                        else:
                            endereco_descriptografado[k] = v  # Manter valor original se não for string válida
                    user_doc['endereco'] = endereco_descriptografado
                    logger.info(f"✅ BUSCAR_USUARIO DEBUG - Endereço descriptografado com sucesso")
                except Exception as e:
                    logger.error(f"❌ BUSCAR_USUARIO DEBUG - Erro geral ao processar endereço: {e}")
                    user_doc['endereco'] = None

            logger.info(f"✅ BUSCAR_USUARIO DEBUG - Retornando usuário: ID={user_doc['id']}, Nome={user_doc.get('nome', 'N/A')}")
            return user_doc
        logger.info(f"❌ BUSCAR_USUARIO DEBUG - Nenhum usuário encontrado com firebase_uid: {firebase_uid}")
        return None
    except Exception as e:
        logger.error(f"Erro ao buscar/descriptografar usuário por firebase_uid {firebase_uid}: {e}")
        import traceback
        logger.error(f"Stack trace completo: {traceback.format_exc()}")
        # Se a descriptografia falhar (ex: chave errada), não retorna dados corrompidos
        return None


def criar_ou_atualizar_usuario(db: firestore.client, user_data: schemas.UsuarioSync) -> Dict:
    """
    Cria ou atualiza um usuário no Firestore, criptografando dados sensíveis.
    Esta função é a única fonte da verdade para a lógica de onboarding.
    """
    negocio_id = user_data.negocio_id

    # Criptografa os dados antes de salvar
    nome_criptografado = encrypt_data(user_data.nome)
    telefone_criptografado = encrypt_data(user_data.telefone) if user_data.telefone else None

    # Fluxo de Super Admin (sem negocio_id)
    is_super_admin_flow = not negocio_id
    if is_super_admin_flow:
        if not db.collection('usuarios').limit(1).get():
            user_dict = {
                "nome": nome_criptografado, 
                "email": user_data.email, 
                "firebase_uid": user_data.firebase_uid,
                "roles": {"platform": "super_admin"}, 
                "fcm_tokens": []
            }
            if telefone_criptografado:
                user_dict['telefone'] = telefone_criptografado
            doc_ref = db.collection('usuarios').document()
            doc_ref.set(user_dict)
            user_dict['id'] = doc_ref.id
            logger.info(f"Novo usuário {user_data.email} criado como Super Admin.")
            
            # Descriptografa para retornar ao usuário
            user_dict['nome'] = user_data.nome
            user_dict['telefone'] = user_data.telefone
            return user_dict
        else:
            raise ValueError("Não é possível se registrar sem um negócio específico.")
    
    # Fluxo multi-tenant
    @firestore.transactional
    def transaction_sync_user(transaction):
        # CRITICAL DEBUG: Verificar usuário existente DENTRO da transação
        logger.info(f"🔍 SYNC DEBUG - Firebase UID: {user_data.firebase_uid}")
        
        # Buscar usuário existente DENTRO da transação para evitar race conditions
        user_query = db.collection('usuarios').where('firebase_uid', '==', user_data.firebase_uid).limit(1)
        user_docs = list(user_query.stream(transaction=transaction))
        
        user_existente = None
        if user_docs:
            user_doc = user_docs[0].to_dict()
            user_doc['id'] = user_docs[0].id
            # Descriptografar campos para uso na lógica com tratamento individual de erros
            user_existente = user_doc
            
            # Descriptografar nome
            if 'nome' in user_doc:
                try:
                    user_doc['nome'] = decrypt_data(user_doc['nome'])
                    logger.info(f"✅ TRANSACAO DEBUG - Nome descriptografado com sucesso")
                except Exception as e:
                    logger.error(f"❌ TRANSACAO DEBUG - Erro ao descriptografar NOME: {e}")
                    user_doc['nome'] = '[Erro na descriptografia do nome]'
            
            # Descriptografar telefone
            if 'telefone' in user_doc and user_doc['telefone']:
                try:
                    user_doc['telefone'] = decrypt_data(user_doc['telefone'])
                    logger.info(f"✅ TRANSACAO DEBUG - Telefone descriptografado com sucesso")
                except Exception as e:
                    logger.error(f"❌ TRANSACAO DEBUG - Erro ao descriptografar TELEFONE: {e}")
                    user_doc['telefone'] = None
            
            # Descriptografar endereço com tratamento de erro robusto
            if 'endereco' in user_doc and user_doc['endereco']:
                try:
                    endereco_descriptografado = {}
                    for k, v in user_doc['endereco'].items():
                        if v and isinstance(v, str) and v.strip():
                            try:
                                endereco_descriptografado[k] = decrypt_data(v)
                            except Exception as field_error:
                                logger.warning(f"⚠️ TRANSACAO DEBUG - Erro ao descriptografar campo '{k}' do endereço: {field_error}")
                                endereco_descriptografado[k] = None
                        else:
                            endereco_descriptografado[k] = v  # Manter valor original se não for string válida
                    user_doc['endereco'] = endereco_descriptografado
                    logger.info(f"✅ TRANSACAO DEBUG - Endereço descriptografado com sucesso")
                except Exception as e:
                    logger.error(f"❌ TRANSACAO DEBUG - Erro geral ao processar endereço: {e}")
                    logger.error(f"❌ TRANSACAO DEBUG - Dados do endereço corrompidos, definindo como None")
                    user_doc['endereco'] = None
        
        logger.info(f"🔍 SYNC DEBUG - Usuário existente encontrado: {user_existente is not None}")
        if user_existente:
            logger.info(f"🔍 SYNC DEBUG - ID do usuário existente: {user_existente.get('id')}")
            logger.info(f"🔍 SYNC DEBUG - Roles atuais: {user_existente.get('roles', {})}")
        
        negocio_doc_ref = db.collection('negocios').document(negocio_id)
        negocio_doc = negocio_doc_ref.get(transaction=transaction)

        if not negocio_doc.exists:
            raise ValueError(f"O negócio com ID '{negocio_id}' não foi encontrado.")

        negocio_data = negocio_doc.to_dict()
        has_admin = negocio_data.get('admin_uid') is not None
        
        role = "cliente"
        if not has_admin and user_data.codigo_convite and user_data.codigo_convite == negocio_data.get('codigo_convite'):
            role = "admin"
        
        if user_existente:
            logger.info(f"✅ SYNC DEBUG - Usuário existe, atualizando roles se necessário")
            user_ref = db.collection('usuarios').document(user_existente['id'])
            current_roles = user_existente.get("roles", {})
            
            if negocio_id not in current_roles:
                logger.info(f"🔄 SYNC DEBUG - Adicionando role '{role}' para negócio {negocio_id}")
                transaction.update(user_ref, {f'roles.{negocio_id}': role})
                user_existente["roles"][negocio_id] = role
                if role == "admin":
                    transaction.update(negocio_doc_ref, {'admin_uid': user_data.firebase_uid})
            else:
                logger.info(f"✅ SYNC DEBUG - Role já existe para este negócio: {current_roles[negocio_id]}")
            
            # CRITICAL: Sempre atualizar dados básicos se necessário
            updates_needed = {}
            if user_existente.get('nome') != user_data.nome:
                updates_needed['nome'] = encrypt_data(user_data.nome)
                logger.info(f"🔄 SYNC DEBUG - Atualizando nome")
            if user_existente.get('email') != user_data.email:
                updates_needed['email'] = user_data.email
                logger.info(f"🔄 SYNC DEBUG - Atualizando email")
            
            if updates_needed:
                transaction.update(user_ref, updates_needed)
                user_existente.update(updates_needed)
                # Descriptografar nome para resposta
                if 'nome' in updates_needed:
                    user_existente['nome'] = user_data.nome
            
            logger.info(f"✅ SYNC DEBUG - Retornando usuário existente ID: {user_existente['id']}")
            logger.info(f"🔍 SYNC DEBUG - FINAL RETURN USER - ID: {user_existente['id']}, Firebase_UID: {user_existente.get('firebase_uid', 'N/A')}")
            return user_existente

        # CRIAR NOVO USUÁRIO
        logger.info(f"🆕 SYNC DEBUG - Criando novo usuário com role '{role}'")
        
        # DOUBLE CHECK: Verificação final antes de criar usuário para prevenir duplicação
        final_check_query = db.collection('usuarios').where('firebase_uid', '==', user_data.firebase_uid).limit(1)
        final_check_docs = list(final_check_query.stream(transaction=transaction))
        if final_check_docs:
            logger.warning(f"⚠️ SYNC DEBUG - Usuário encontrado na verificação final! Usando usuário existente em vez de criar novo.")
            existing_doc = final_check_docs[0].to_dict()
            existing_doc['id'] = final_check_docs[0].id
            # Descriptografar e retornar usuário existente
            try:
                if 'nome' in existing_doc:
                    existing_doc['nome'] = decrypt_data(existing_doc['nome'])
                if 'telefone' in existing_doc and existing_doc['telefone']:
                    existing_doc['telefone'] = decrypt_data(existing_doc['telefone'])
                return existing_doc
            except Exception as e:
                logger.error(f"Erro ao descriptografar usuário na verificação final: {e}")
        
        user_dict = {
            "nome": nome_criptografado, 
            "email": user_data.email, 
            "firebase_uid": user_data.firebase_uid,
            "roles": {negocio_id: role}, 
            "fcm_tokens": []
        }
        if telefone_criptografado:
            user_dict['telefone'] = telefone_criptografado
        if hasattr(user_data, 'endereco') and user_data.endereco:
            # O ideal é criptografar campo a campo do endereço
            user_dict['endereco'] = {k: encrypt_data(v) for k, v in user_data.endereco.dict().items()}
        
        new_user_ref = db.collection('usuarios').document()
        transaction.set(new_user_ref, user_dict)
        user_dict['id'] = new_user_ref.id

        if role == "admin":
            transaction.update(negocio_doc_ref, {'admin_uid': user_data.firebase_uid})
        
        # Descriptografa para retornar ao usuário
        user_dict['nome'] = user_data.nome
        user_dict['telefone'] = user_data.telefone
        if 'endereco' in user_dict and user_dict['endereco']:
             user_dict['endereco'] = user_data.endereco.dict()

        logger.info(f"🔍 SYNC DEBUG - NOVO USUARIO CRIADO - ID: {user_dict['id']}, Firebase_UID: {user_dict.get('firebase_uid', 'N/A')}")
        return user_dict
    
    # Executar como transação Firestore
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

# def admin_listar_usuarios_por_negocio(db: firestore.client, negocio_id: str, status: str = 'ativo') -> List[Dict]:
#     """
#     Lista todos os usuários de um negócio, enriquecendo os dados com os IDs de
#     vínculos de profissionais, enfermeiros e técnicos quando aplicável.
#     """
#     usuarios = []
#     try:
#         query = db.collection('usuarios').where(f'roles.{negocio_id}', 'in', ['cliente', 'profissional', 'admin', 'tecnico'])

#         for doc in query.stream():
#             usuario_data = doc.to_dict()
#             status_no_negocio = usuario_data.get('status_por_negocio', {}).get(negocio_id, 'ativo')

#             if status_no_negocio == status:
#                 usuario_data['id'] = doc.id
#                 user_role = usuario_data.get("roles", {}).get(negocio_id)

#                 # --- LÓGICA DE ENRIQUECIMENTO DE DADOS ---

#                 # 1. Para Profissionais e Admins, adiciona o profissional_id
#                 if user_role in ['profissional', 'admin']:
#                     firebase_uid = usuario_data.get('firebase_uid')
#                     if firebase_uid:
#                         perfil_profissional = buscar_profissional_por_uid(db, negocio_id, firebase_uid)
#                         usuario_data['profissional_id'] = perfil_profissional.get('id') if perfil_profissional else None
#                     else:
#                         usuario_data['profissional_id'] = None
                
#                 # 2. Para Clientes (Pacientes), adiciona os IDs dos profissionais vinculados
#                 elif user_role == 'cliente':
#                     # Adiciona o ID do enfermeiro vinculado (convertido para profissional_id)
#                     enfermeiro_user_id = usuario_data.get('enfermeiro_id')
#                     if enfermeiro_user_id:
#                         enfermeiro_doc = db.collection('usuarios').document(enfermeiro_user_id).get()
#                         if enfermeiro_doc.exists:
#                             firebase_uid_enfermeiro = enfermeiro_doc.to_dict().get('firebase_uid')
#                             perfil_enfermeiro = buscar_profissional_por_uid(db, negocio_id, firebase_uid_enfermeiro)
#                             usuario_data['enfermeiro_vinculado_id'] = perfil_enfermeiro.get('id') if perfil_enfermeiro else None
#                         else:
#                             usuario_data['enfermeiro_vinculado_id'] = None
#                     else:
#                         usuario_data['enfermeiro_vinculado_id'] = None

#                     # Adiciona a lista de IDs de técnicos vinculados
#                     usuario_data['tecnicos_vinculados_ids'] = usuario_data.get('tecnicos_ids', [])

#                 usuarios.append(usuario_data)

#         return usuarios
#     except Exception as e:
#         logger.error(f"Erro ao listar usuários para o negocio_id {negocio_id}: {e}")
#         return []

# def admin_set_paciente_status(db: firestore.client, negocio_id: str, paciente_id: str, status: str, autor_uid: str) -> Optional[Dict]:
#     """Define o status de um paciente ('ativo' ou 'arquivado') em um negócio."""
#     if status not in ['ativo', 'arquivado']:
#         raise ValueError("Status inválido. Use 'ativo' ou 'arquivado'.")

#     user_ref = db.collection('usuarios').document(paciente_id)
#     status_path = f'status_por_negocio.{negocio_id}'
#     user_ref.update({status_path: status})

#     criar_log_auditoria(
#         db,
#         autor_uid=autor_uid,
#         negocio_id=negocio_id,
#         acao=f"PACIENTE_STATUS_{status.upper()}",
#         detalhes={"paciente_alvo_id": paciente_id}
#     )

#     logger.info(f"Status do paciente {paciente_id} definido como '{status}' no negócio {negocio_id}.")

#     doc = user_ref.get()
#     if doc.exists:
#         data = doc.to_dict()
#         data['id'] = doc.id
#         return data
#     return None


def admin_listar_usuarios_por_negocio(db: firestore.client, negocio_id: str, status: str = 'ativo') -> List[Dict]:
    """
    Lista todos os usuários de um negócio, com filtro de status.
    VERSÃO FINAL: Retorna o campo de status corretamente para cada usuário.
    """
    usuarios = []
    try:
        query = db.collection('usuarios').where(f'roles.{negocio_id}', 'in', ['cliente', 'profissional', 'admin', 'tecnico', 'medico'])

        for doc in query.stream():
            usuario_data = doc.to_dict()
            
            # Pega o status do usuário para o negócio específico, com 'ativo' como padrão.
            status_no_negocio = usuario_data.get('status_por_negocio', {}).get(negocio_id, 'ativo')
            
            # LÓGICA DE FILTRO (continua a mesma)
            deve_incluir = False
            if status == 'all':
                deve_incluir = True
            elif status_no_negocio == status:
                deve_incluir = True

            if deve_incluir:
                usuario_data['id'] = doc.id
                
                # Descriptografa campos sensíveis do usuário
                if 'nome' in usuario_data and usuario_data['nome']:
                    try:
                        usuario_data['nome'] = decrypt_data(usuario_data['nome'])
                    except Exception as e:
                        logger.error(f"Erro ao descriptografar nome do usuário {doc.id}: {e}")
                        usuario_data['nome'] = "[Erro na descriptografia]"
                
                if 'telefone' in usuario_data and usuario_data['telefone']:
                    try:
                        usuario_data['telefone'] = decrypt_data(usuario_data['telefone'])
                    except Exception as e:
                        logger.error(f"Erro ao descriptografar telefone do usuário {doc.id}: {e}")
                        usuario_data['telefone'] = "[Erro na descriptografia]"
                
                if 'endereco' in usuario_data and usuario_data['endereco']:
                    endereco_descriptografado = {}
                    for key, value in usuario_data['endereco'].items():
                        if value and isinstance(value, str) and value.strip():
                            try:
                                endereco_descriptografado[key] = decrypt_data(value)
                            except Exception as e:
                                logger.error(f"Erro ao descriptografar campo de endereço {key} do usuário {doc.id}: {e}")
                                endereco_descriptografado[key] = "[Erro na descriptografia]"
                        else:
                            endereco_descriptografado[key] = value
                    usuario_data['endereco'] = endereco_descriptografado
                
                # ***** A CORREÇÃO ESTÁ AQUI *****
                # Adiciona o status do negócio ao dicionário de resposta.
                # O nome do campo foi corrigido no schema para 'status_por_negocio' para ser mais claro.
                # Esta linha garante que o dado seja populado na resposta da API.
                usuario_data['status_por_negocio'] = {negocio_id: status_no_negocio}

                # A lógica de enriquecimento de dados continua a mesma...
                user_role = usuario_data.get("roles", {}).get(negocio_id)
                if user_role in ['profissional', 'admin']:
                    firebase_uid = usuario_data.get('firebase_uid')
                    if firebase_uid:
                        perfil_profissional = buscar_profissional_por_uid(db, negocio_id, firebase_uid)
                        usuario_data['profissional_id'] = perfil_profissional.get('id') if perfil_profissional else None
                elif user_role == 'cliente':
                    enfermeiro_user_id = usuario_data.get('enfermeiro_id')
                    if enfermeiro_user_id:
                        enfermeiro_doc = db.collection('usuarios').document(enfermeiro_user_id).get()
                        if enfermeiro_doc.exists:
                            firebase_uid_enfermeiro = enfermeiro_doc.to_dict().get('firebase_uid')
                            perfil_enfermeiro = buscar_profissional_por_uid(db, negocio_id, firebase_uid_enfermeiro)
                            usuario_data['enfermeiro_vinculado_id'] = perfil_enfermeiro.get('id') if perfil_enfermeiro else None
                    usuario_data['tecnicos_vinculados_ids'] = usuario_data.get('tecnicos_ids', [])

                usuarios.append(usuario_data)

        return usuarios
    except Exception as e:
        logger.error(f"Erro ao listar usuários para o negocio_id {negocio_id}: {e}")
        return []

def admin_set_usuario_status(db: firestore.client, negocio_id: str, user_id: str, status: str, autor_uid: str) -> Optional[Dict]:
    """Define o status de um usuário ('ativo' ou 'inativo') em um negócio."""
    if status not in ['ativo', 'inativo']:
        raise ValueError("Status inválido. Use 'ativo' ou 'inativo'.")

    user_ref = db.collection('usuarios').document(user_id)
    status_path = f'status_por_negocio.{negocio_id}'
    user_ref.update({status_path: status})

    criar_log_auditoria(
        db,
        autor_uid=autor_uid,
        negocio_id=negocio_id,
        acao=f"USUARIO_STATUS_{status.upper()}",
        detalhes={"usuario_alvo_id": user_id}
    )
    logger.info(f"Status do usuário {user_id} definido como '{status}' no negócio {negocio_id}.")

    doc = user_ref.get()
    if doc.exists:
        data = doc.to_dict()
        data['id'] = doc.id
        
        # Descriptografa campos sensíveis do usuário
        if 'nome' in data and data['nome']:
            try:
                data['nome'] = decrypt_data(data['nome'])
            except Exception as e:
                logger.error(f"Erro ao descriptografar nome do usuário {doc.id}: {e}")
                data['nome'] = "[Erro na descriptografia]"
        
        if 'telefone' in data and data['telefone']:
            try:
                data['telefone'] = decrypt_data(data['telefone'])
            except Exception as e:
                logger.error(f"Erro ao descriptografar telefone do usuário {doc.id}: {e}")
                data['telefone'] = "[Erro na descriptografia]"
        
        if 'endereco' in data and data['endereco']:
            endereco_descriptografado = {}
            for key, value in data['endereco'].items():
                if value and isinstance(value, str) and value.strip():
                    try:
                        endereco_descriptografado[key] = decrypt_data(value)
                    except Exception as e:
                        logger.error(f"Erro ao descriptografar campo de endereço {key} do usuário {doc.id}: {e}")
                        endereco_descriptografado[key] = "[Erro na descriptografia]"
                else:
                    endereco_descriptografado[key] = value
            data['endereco'] = endereco_descriptografado
        
        return data
    return None

def admin_atualizar_role_usuario(db: firestore.client, negocio_id: str, user_id: str, novo_role: str, autor_uid: str) -> Optional[Dict]:
    """
    Atualiza a role de um usuário dentro de um negócio específico.
    Cria/desativa o perfil profissional conforme necessário.
    """
    # --- ALTERAÇÃO AQUI: Adicionando 'medico' à lista de roles válidas ---
    if novo_role not in ['cliente', 'profissional', 'admin', 'tecnico', 'medico']:
        raise ValueError("Role inválida. As roles permitidas são 'cliente', 'profissional', 'admin', 'tecnico' e 'medico'.")
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

    elif novo_role == 'cliente' or novo_role == 'tecnico' or novo_role == 'medico': # Desativa perfil se virar cliente, tecnico ou medico
        if perfil_profissional and perfil_profissional.get('ativo'):
            # Desativa o perfil profissional se existir e estiver ativo
            prof_ref = db.collection('profissionais').document(perfil_profissional['id'])
            prof_ref.update({"ativo": False})
            logger.info(f"Perfil profissional desativado para o usuário {user_data['email']} no negócio {negocio_id}.")

    logger.info(f"Role do usuário {user_data['email']} atualizada para '{novo_role}' no negócio {negocio_id}.")

    updated_user_doc = user_ref.get()
    updated_user_data = updated_user_doc.to_dict()
    updated_user_data['id'] = updated_user_doc.id
    
    # Descriptografa campos sensíveis do usuário
    if 'nome' in updated_user_data and updated_user_data['nome']:
        try:
            updated_user_data['nome'] = decrypt_data(updated_user_data['nome'])
        except Exception as e:
            logger.error(f"Erro ao descriptografar nome do usuário {updated_user_doc.id}: {e}")
            updated_user_data['nome'] = "[Erro na descriptografia]"
    
    if 'telefone' in updated_user_data and updated_user_data['telefone']:
        try:
            updated_user_data['telefone'] = decrypt_data(updated_user_data['telefone'])
        except Exception as e:
            logger.error(f"Erro ao descriptografar telefone do usuário {updated_user_doc.id}: {e}")
            updated_user_data['telefone'] = "[Erro na descriptografia]"
    
    if 'endereco' in updated_user_data and updated_user_data['endereco']:
        endereco_descriptografado = {}
        for key, value in updated_user_data['endereco'].items():
            if value and isinstance(value, str) and value.strip():
                try:
                    endereco_descriptografado[key] = decrypt_data(value)
                except Exception as e:
                    logger.error(f"Erro ao descriptografar campo de endereço {key} do usuário {updated_user_doc.id}: {e}")
                    endereco_descriptografado[key] = "[Erro na descriptografia]"
            else:
                endereco_descriptografado[key] = value
        updated_user_data['endereco'] = endereco_descriptografado
    
    return updated_user_data

def admin_criar_paciente(db: firestore.client, negocio_id: str, paciente_data: schemas.PacienteCreateByAdmin) -> Dict:
    """
    (Admin ou Enfermeiro) Cria um novo usuário de paciente no Firebase Auth e o sincroniza no Firestore,
    lidando corretamente com o endereço como um campo exclusivo do paciente.
    """
    # 1. Criar usuário no Firebase Auth (lógica inalterada)
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

    # 2. Sincronizar o usuário no Firestore, SEM o endereço.
    # O schema UsuarioSync não tem mais o campo 'endereco'.
    sync_data = schemas.UsuarioSync(
        nome=paciente_data.nome,
        email=paciente_data.email,
        firebase_uid=firebase_user.uid,
        negocio_id=negocio_id,
        telefone=paciente_data.telefone
    )

    try:
        # Cria o perfil básico do usuário (sem endereço)
        user_profile = criar_ou_atualizar_usuario(db, sync_data)
        
        # 3. Se um endereço foi fornecido na requisição, ATUALIZA o documento recém-criado
        if paciente_data.endereco:
            logger.info(f"Adicionando endereço ao paciente recém-criado: {user_profile['id']}")
            # Chama a função específica para adicionar/atualizar o endereço
            atualizar_endereco_paciente(db, user_profile['id'], paciente_data.endereco)
            # Adiciona o endereço ao dicionário de resposta para consistência
            user_profile['endereco'] = paciente_data.endereco.model_dump()
        
        # 4. Adicionar dados pessoais básicos se fornecidos
        dados_pessoais_update = {}
        if paciente_data.data_nascimento:
            dados_pessoais_update['data_nascimento'] = paciente_data.data_nascimento
        if paciente_data.sexo:
            dados_pessoais_update['sexo'] = paciente_data.sexo
        if paciente_data.estado_civil:
            dados_pessoais_update['estado_civil'] = paciente_data.estado_civil
        if paciente_data.profissao:
            dados_pessoais_update['profissao'] = paciente_data.profissao
            
        if dados_pessoais_update:
            logger.info(f"Adicionando dados pessoais ao paciente recém-criado: {user_profile['id']}")
            # Atualizar documento com dados pessoais
            user_ref = db.collection('usuarios').document(user_profile['id'])
            user_ref.update(dados_pessoais_update)
            # Adicionar aos dados de resposta
            user_profile.update(dados_pessoais_update)

        logger.info(f"Perfil do paciente {paciente_data.email} sincronizado com sucesso no Firestore.")
        return user_profile

    except Exception as e:
        # A lógica de reversão em caso de erro continua a mesma
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
                
                # Descriptografa campos sensíveis do cliente
                if 'nome' in cliente_data and cliente_data['nome']:
                    try:
                        cliente_data['nome'] = decrypt_data(cliente_data['nome'])
                    except Exception as e:
                        logger.error(f"Erro ao descriptografar nome do cliente {doc.id}: {e}")
                        cliente_data['nome'] = "[Erro na descriptografia]"
                
                if 'telefone' in cliente_data and cliente_data['telefone']:
                    try:
                        cliente_data['telefone'] = decrypt_data(cliente_data['telefone'])
                    except Exception as e:
                        logger.error(f"Erro ao descriptografar telefone do cliente {doc.id}: {e}")
                        cliente_data['telefone'] = "[Erro na descriptografia]"
                
                if 'endereco' in cliente_data and cliente_data['endereco']:
                    endereco_descriptografado = {}
                    for key, value in cliente_data['endereco'].items():
                        if value and isinstance(value, str) and value.strip():
                            try:
                                endereco_descriptografado[key] = decrypt_data(value)
                            except Exception as e:
                                logger.error(f"Erro ao descriptografar campo de endereço {key} do cliente {doc.id}: {e}")
                                endereco_descriptografado[key] = "[Erro na descriptografia]"
                        else:
                            endereco_descriptografado[key] = value
                    cliente_data['endereco'] = endereco_descriptografado
                
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

# Em crud.py

# Em crud.py

# Em crud.py

def listar_profissionais_por_negocio(db: firestore.client, negocio_id: str) -> List[Dict]:
    """Lista todos os profissionais ativos de um negócio específico, enriquecendo com dados do usuário."""
    profissionais = []
    try:
        query = db.collection('profissionais').where('negocio_id', '==', negocio_id).where('ativo', '==', True)
        
        for doc in query.stream():
            prof_data = doc.to_dict()
            prof_data['id'] = doc.id

            firebase_uid = prof_data.get('usuario_uid')
            logger.info(f"🔍 DEBUG PROFISSIONAL - ID: {prof_data.get('id')}, usuario_uid: {firebase_uid}")

            # --- INÍCIO DA CORREÇÃO ---
            # Busca os dados do usuário, mas não pula o profissional se não encontrar
            if firebase_uid:
                usuario_doc = buscar_usuario_por_firebase_uid(db, firebase_uid)
                if usuario_doc:
                    prof_data['nome'] = usuario_doc.get('nome', prof_data.get('nome'))
                    # Tenta buscar a imagem do usuário em diferentes campos possíveis
                    user_image = (usuario_doc.get('profile_image_url') or
                                 usuario_doc.get('profile_image') or
                                 prof_data.get('fotos', {}).get('thumbnail'))
                    prof_data['profile_image_url'] = user_image
                    logger.info(f"🖼️ PROFISSIONAL DEBUG - Profissional {prof_data.get('id')}: user_image_url={usuario_doc.get('profile_image_url')}, user_image={usuario_doc.get('profile_image')}, prof_fotos_thumbnail={prof_data.get('fotos', {}).get('thumbnail')}, final_image={user_image}")
                    prof_data['email'] = usuario_doc.get('email', '')
                else:
                    # Fallback se o usuário não for encontrado
                    prof_fallback_image = (prof_data.get('fotos', {}).get('thumbnail') or
                                         prof_data.get('fotos', {}).get('perfil') or
                                         prof_data.get('fotos', {}).get('original'))
                    prof_data['profile_image_url'] = prof_fallback_image
                    prof_data['email'] = ''
                    logger.info(f"🖼️ PROFISSIONAL DEBUG - Profissional {prof_data.get('id')} (sem usuário): prof_fotos={prof_data.get('fotos', {})}, final_image={prof_fallback_image}")
            else:
                # Fallback se não houver firebase_uid
                prof_fallback_image = (prof_data.get('fotos', {}).get('thumbnail') or
                                     prof_data.get('fotos', {}).get('perfil') or
                                     prof_data.get('fotos', {}).get('original'))
                prof_data['profile_image_url'] = prof_fallback_image
                prof_data['email'] = ''
                logger.info(f"🖼️ PROFISSIONAL DEBUG - Profissional {prof_data.get('id')} (sem firebase_uid): prof_fotos={prof_data.get('fotos', {})}, final_image={prof_fallback_image}")
            
            # Garante que o firebase_uid sempre esteja na resposta
            prof_data['firebase_uid'] = firebase_uid
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
    logger_prefix: str = "",
    notification_title: str = None,
    notification_body: str = None
) -> None:
    """
    Envia mensagens FCM com notification e data objects.
    Remove tokens inválidos (Unregistered) do usuário.
    """
    successes = 0
    failures = 0

    for t in list(tokens or []):
        try:
            # Constrói a mensagem com notification e data objects
            message_kwargs = {"data": data_dict, "token": t}

            # Adiciona notification object se título e corpo forem fornecidos
            if notification_title and notification_body:
                message_kwargs["notification"] = messaging.Notification(
                    title=notification_title,
                    body=notification_body
                )

            messaging.send(messaging.Message(**message_kwargs))
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

    # Enriquecer profissional com dados do usuário (nome descriptografado) ANTES de construir agendamento_dict
    firebase_uid = profissional.get('usuario_uid')
    nome_profissional_real = profissional.get('nome', 'Profissional')
    if firebase_uid:
        usuario_doc = buscar_usuario_por_firebase_uid(db, firebase_uid)
        if usuario_doc:
            nome_profissional_real = usuario_doc.get('nome', nome_profissional_real)
            logger.info(f"🔧 AGENDAMENTO - Nome do profissional enriquecido: {nome_profissional_real}")
        else:
            logger.warning(f"🔧 AGENDAMENTO - Usuário não encontrado para firebase_uid: {firebase_uid}")

    # Enriquecer cliente com dados reais do usuário
    nome_cliente_real = cliente.nome
    cliente_doc = buscar_usuario_por_firebase_uid(db, cliente.firebase_uid)
    if cliente_doc:
        nome_cliente_real = cliente_doc.get('nome', cliente.nome)
        logger.info(f"🔧 AGENDAMENTO - Nome do cliente enriquecido: {nome_cliente_real}")

    agendamento_dict = {
        "negocio_id": agendamento_data.negocio_id,
        "data_hora": agendamento_data.data_hora,
        "status": "pendente",
        "cliente_id": cliente.id,
        "cliente_nome": nome_cliente_real,
        "profissional_id": profissional['id'],
        "profissional_nome": nome_profissional_real,
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
                    logger_prefix="[Novo agendamento] ",
                    notification_title="Novo Agendamento!",
                    notification_body=mensagem_body
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
                        logger_prefix="[Cancelamento pelo cliente] ",
                        notification_title="Agendamento Cancelado",
                        notification_body=mensagem_body
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


def confirmar_agendamento_pelo_profissional(db: firestore.client, agendamento_id: str, profissional_id: str) -> Optional[Dict]:
    """
    Permite a um profissional confirmar um agendamento, atualizando o status
    de 'pendente' para 'confirmado' e notificando o cliente.
    """
    agendamento_ref = db.collection('agendamentos').document(agendamento_id)
    agendamento_doc = agendamento_ref.get()

    if not agendamento_doc.exists:
        logger.warning(f"Tentativa de confirmar agendamento inexistente: {agendamento_id}")
        return None

    agendamento = agendamento_doc.to_dict()
    agendamento['id'] = agendamento_doc.id

    if agendamento.get('profissional_id') != profissional_id:
        logger.warning(f"Profissional {profissional_id} tentou confirmar agendamento {agendamento_id} sem permissão.")
        return None  # Profissional não autorizado

    # Verifica se o agendamento está pendente
    if agendamento.get('status') != 'pendente':
        logger.warning(f"Tentativa de confirmar agendamento {agendamento_id} com status '{agendamento.get('status')}'. Apenas agendamentos pendentes podem ser confirmados.")
        return None

    # Atualiza o status
    agendamento_ref.update({"status": "confirmado"})
    agendamento["status"] = "confirmado"
    logger.info(f"Agendamento {agendamento_id} confirmado pelo profissional {profissional_id}.")

    # Dispara a notificação para o cliente
    _notificar_cliente_confirmacao(db, agendamento, agendamento_id)

    return agendamento


def listar_agendamentos_por_cliente(db: firestore.client, negocio_id: str, cliente_id: str) -> List[Dict]:
    """Lista os agendamentos de um cliente em um negócio específico."""
    agendamentos = []
    query = db.collection('agendamentos').where('negocio_id', '==', negocio_id).where('cliente_id', '==', cliente_id).order_by('data_hora', direction=firestore.Query.DESCENDING)
    
    for doc in query.stream():
        ag_data = doc.to_dict()
        ag_data['id'] = doc.id
        
        # Descriptografa nomes se estiverem criptografados (detecta pelo padrão gAAAAA)
        if 'cliente_nome' in ag_data and ag_data['cliente_nome']:
            cliente_nome = ag_data['cliente_nome']
            if isinstance(cliente_nome, str) and cliente_nome.startswith('gAAAAA'):
                try:
                    ag_data['cliente_nome'] = decrypt_data(cliente_nome)
                    logger.info(f"🔓 Cliente nome descriptografado no agendamento {doc.id}")
                except Exception as e:
                    logger.error(f"Erro ao descriptografar cliente_nome no agendamento {doc.id}: {e}")
                    ag_data['cliente_nome'] = "[Erro na descriptografia]"
            # Se não começa com gAAAAA, mantém o valor original (não criptografado)

        if 'profissional_nome' in ag_data and ag_data['profissional_nome']:
            profissional_nome = ag_data['profissional_nome']
            if isinstance(profissional_nome, str) and profissional_nome.startswith('gAAAAA'):
                try:
                    ag_data['profissional_nome'] = decrypt_data(profissional_nome)
                    logger.info(f"🔓 Profissional nome descriptografado no agendamento {doc.id}")
                except Exception as e:
                    logger.error(f"Erro ao descriptografar profissional_nome no agendamento {doc.id}: {e}")
                    ag_data['profissional_nome'] = "[Erro na descriptografia]"
            # Se não começa com gAAAAA, mantém o valor original (não criptografado)
        
        agendamentos.append(ag_data)
    
    return agendamentos

def listar_agendamentos_por_profissional(db: firestore.client, negocio_id: str, profissional_id: str) -> List[Dict]:
    """Lista os agendamentos de um profissional em um negócio específico."""
    agendamentos = []
    query = db.collection('agendamentos').where('negocio_id', '==', negocio_id).where('profissional_id', '==', profissional_id).order_by('data_hora', direction=firestore.Query.DESCENDING)
    
    for doc in query.stream():
        ag_data = doc.to_dict()
        ag_data['id'] = doc.id
        
        # Descriptografa nomes se estiverem criptografados (detecta pelo padrão gAAAAA)
        if 'cliente_nome' in ag_data and ag_data['cliente_nome']:
            cliente_nome = ag_data['cliente_nome']
            if isinstance(cliente_nome, str) and cliente_nome.startswith('gAAAAA'):
                try:
                    ag_data['cliente_nome'] = decrypt_data(cliente_nome)
                    logger.info(f"🔓 Cliente nome descriptografado no agendamento {doc.id}")
                except Exception as e:
                    logger.error(f"Erro ao descriptografar cliente_nome no agendamento {doc.id}: {e}")
                    ag_data['cliente_nome'] = "[Erro na descriptografia]"
            # Se não começa com gAAAAA, mantém o valor original (não criptografado)

        if 'profissional_nome' in ag_data and ag_data['profissional_nome']:
            profissional_nome = ag_data['profissional_nome']
            if isinstance(profissional_nome, str) and profissional_nome.startswith('gAAAAA'):
                try:
                    ag_data['profissional_nome'] = decrypt_data(profissional_nome)
                    logger.info(f"🔓 Profissional nome descriptografado no agendamento {doc.id}")
                except Exception as e:
                    logger.error(f"Erro ao descriptografar profissional_nome no agendamento {doc.id}: {e}")
                    ag_data['profissional_nome'] = "[Erro na descriptografia]"
            # Se não começa com gAAAAA, mantém o valor original (não criptografado)
        
        agendamentos.append(ag_data)
        
    return agendamentos

# =================================================================================
# FUNÇÕES DE FEED E INTERAÇÕES
# =================================================================================

def criar_postagem(db: firestore.client, postagem_data: schemas.PostagemCreate, profissional: Dict) -> Dict:
    """Cria uma nova postagem, desnormalizando os dados do profissional."""

    # Enriquecer profissional com dados do usuário (nome descriptografado)
    firebase_uid = profissional.get('usuario_uid')
    if firebase_uid:
        usuario_doc = buscar_usuario_por_firebase_uid(db, firebase_uid)
        if usuario_doc:
            profissional['nome'] = usuario_doc.get('nome', profissional.get('nome'))
            logger.info(f"🔧 POSTAGEM - Nome do profissional enriquecido: {usuario_doc.get('nome', 'N/A')}")

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
        
        # Mapear campos para compatibilidade com schema
        # Se tem 'titulo', mapear para 'title'
        if 'titulo' in notificacao_data and 'title' not in notificacao_data:
            notificacao_data['title'] = notificacao_data['titulo']
        
        # Se tem 'corpo', mapear para 'body'  
        if 'corpo' in notificacao_data and 'body' not in notificacao_data:
            notificacao_data['body'] = notificacao_data['corpo']
            
        # Garantir campos obrigatórios estão presentes e não são null
        if 'title' not in notificacao_data or notificacao_data['title'] is None:
            notificacao_data['title'] = notificacao_data.get('titulo', 'Notificação')

        if 'body' not in notificacao_data or notificacao_data['body'] is None:
            notificacao_data['body'] = notificacao_data.get('corpo', 'Conteúdo da notificação')

        # Garantir campo 'lida' existe e não é null
        if 'lida' not in notificacao_data or notificacao_data['lida'] is None:
            notificacao_data['lida'] = False

        # Garantir campo 'data_criacao' existe e não é null
        if 'data_criacao' not in notificacao_data or notificacao_data['data_criacao'] is None:
            notificacao_data['data_criacao'] = firestore.SERVER_TIMESTAMP

        # Garantir que campos string não sejam null
        if notificacao_data['title'] is None:
            notificacao_data['title'] = 'Notificação'
        if notificacao_data['body'] is None:
            notificacao_data['body'] = 'Conteúdo da notificação'
        if 'tipo' in notificacao_data and notificacao_data['tipo'] is None:
            notificacao_data['tipo'] = 'GERAL'
        
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
                logger_prefix="[Cancelamento pelo profissional] ",
                notification_title="Agendamento Cancelado",
                notification_body=mensagem_body
            )
        else:
            logger.info(f"Cliente {cliente_id} não possui tokens FCM para notificar.")

    except Exception as e:
        logger.error(f"Falha crítica na função _notificar_cliente_cancelamento para agendamento {agendamento_id}: {e}")


def _notificar_cliente_confirmacao(db: firestore.client, agendamento: Dict, agendamento_id: str):
    """Envia notificação para o cliente sobre a confirmação do agendamento."""
    try:
        cliente_id = agendamento.get('cliente_id')
        if not cliente_id:
            logger.warning(f"Agendamento {agendamento_id} sem cliente_id. Não é possível notificar.")
            return

        cliente_doc_ref = db.collection('usuarios').document(cliente_id)
        cliente_doc = cliente_doc_ref.get()

        if not cliente_doc.exists:
            logger.error(f"Documento do cliente {cliente_id} não encontrado para notificação de confirmação.")
            return

        cliente_data = cliente_doc.to_dict()
        cliente_data['id'] = cliente_doc.id

        data_formatada = agendamento['data_hora'].strftime('%d/%m/%Y às %H:%M')
        mensagem_body = f"Seu agendamento com {agendamento['profissional_nome']} para {data_formatada} foi confirmado."

        # 1. Persistir a notificação no Firestore
        notificacao_id = f"AGENDAMENTO_CONFIRMADO:{agendamento_id}"
        notificacao_doc_ref = cliente_doc_ref.collection('notificacoes').document(notificacao_id)

        notificacao_doc_ref.set({
            "title": "Agendamento Confirmado",
            "body": mensagem_body,
            "tipo": "AGENDAMENTO_CONFIRMADO",
            "relacionado": { "agendamento_id": agendamento_id },
            "lida": False,
            "data_criacao": firestore.SERVER_TIMESTAMP,
            "dedupe_key": notificacao_id
        })
        logger.info(f"Notificação de confirmação (prof.) PERSISTIDA para o cliente {cliente_id}.")

        # 2. Enviar a notificação via FCM
        fcm_tokens = cliente_data.get('fcm_tokens')
        if fcm_tokens:
            data_payload = {
                "tipo": "AGENDAMENTO_CONFIRMADO",
                "agendamento_id": agendamento_id,
                "click_action": f"/agendamentos/{agendamento_id}"
            }

            message = messaging.MulticastMessage(
                notification=messaging.Notification(title="Agendamento Confirmado", body=mensagem_body),
                data=data_payload,
                tokens=fcm_tokens
            )

            response = messaging.send_multicast(message)
            logger.info(f"Notificação FCM de confirmação enviada para {len(fcm_tokens)} token(s) do cliente {cliente_id}. Sucessos: {response.success_count}")
        else:
            logger.info(f"Cliente {cliente_id} não possui tokens FCM para notificar.")

    except Exception as e:
        logger.error(f"Falha crítica na função _notificar_cliente_confirmacao para agendamento {agendamento_id}: {e}")


# =================================================================================
# FUNÇÕES DO MÓDULO CLÍNICO
# =================================================================================

# Correção na função para garantir que o ID do documento 'usuarios' seja sempre usado
def vincular_paciente_enfermeiro(db: firestore.client, negocio_id: str, paciente_id: str, enfermeiro_id: Optional[str], autor_uid: str) -> Optional[Dict]:
    """Vincula ou desvincula um paciente de um enfermeiro."""
    paciente_ref = db.collection('usuarios').document(paciente_id)

    # Obter enfermeiro atual antes da atualização
    paciente_doc_atual = paciente_ref.get()
    enfermeiro_atual_id = paciente_doc_atual.to_dict().get('enfermeiro_id') if paciente_doc_atual.exists else None

    # LÓGICA DE DESVINCULAÇÃO
    if enfermeiro_id is None:
        paciente_ref.update({'enfermeiro_id': firestore.DELETE_FIELD})

        # CORREÇÃO: Remover paciente da lista do enfermeiro anterior
        if enfermeiro_atual_id:
            try:
                enfermeiro_ref = db.collection('usuarios').document(enfermeiro_atual_id)
                enfermeiro_ref.update({
                    'pacientes_ids': firestore.ArrayRemove([paciente_id])
                })
                logger.info(f"Paciente {paciente_id} removido da lista do enfermeiro {enfermeiro_atual_id}")
            except Exception as e:
                logger.error(f"Erro ao remover paciente {paciente_id} do enfermeiro {enfermeiro_atual_id}: {e}")

        acao_log = "DESVINCULO_PACIENTE_ENFERMEIRO"
        detalhes_log = {"paciente_id": paciente_id}
        logger.info(f"Paciente {paciente_id} desvinculado do enfermeiro.")
    # LÓGICA DE VINCULAÇÃO (existente)
    else:
        # (A lógica para encontrar o ID do usuário do enfermeiro continua a mesma)
        perfil_enfermeiro = buscar_profissional_por_id(db, enfermeiro_id)
        if not perfil_enfermeiro: return None
        usuario_enfermeiro = buscar_usuario_por_firebase_uid(db, perfil_enfermeiro['usuario_uid'])
        if not usuario_enfermeiro: return None

        usuario_enfermeiro_id_para_salvar = usuario_enfermeiro['id']
        paciente_ref.update({'enfermeiro_id': usuario_enfermeiro_id_para_salvar})

        # CORREÇÃO: Remover paciente do enfermeiro anterior (se existir)
        if enfermeiro_atual_id and enfermeiro_atual_id != usuario_enfermeiro_id_para_salvar:
            try:
                enfermeiro_anterior_ref = db.collection('usuarios').document(enfermeiro_atual_id)
                enfermeiro_anterior_ref.update({
                    'pacientes_ids': firestore.ArrayRemove([paciente_id])
                })
                logger.info(f"Paciente {paciente_id} removido da lista do enfermeiro anterior {enfermeiro_atual_id}")
            except Exception as e:
                logger.error(f"Erro ao remover paciente {paciente_id} do enfermeiro anterior {enfermeiro_atual_id}: {e}")

        # CORREÇÃO: Adicionar paciente à lista do novo enfermeiro
        try:
            enfermeiro_ref = db.collection('usuarios').document(usuario_enfermeiro_id_para_salvar)
            enfermeiro_ref.update({
                'pacientes_ids': firestore.ArrayUnion([paciente_id])
            })
            logger.info(f"Paciente {paciente_id} adicionado à lista do enfermeiro {usuario_enfermeiro_id_para_salvar}")
        except Exception as e:
            logger.error(f"Erro ao adicionar paciente {paciente_id} ao enfermeiro {usuario_enfermeiro_id_para_salvar}: {e}")

        acao_log = "VINCULO_PACIENTE_ENFERMEIRO"
        detalhes_log = {"paciente_id": paciente_id, "enfermeiro_id": usuario_enfermeiro_id_para_salvar}
        logger.info(f"Paciente {paciente_id} vinculado ao enfermeiro {usuario_enfermeiro_id_para_salvar}.")

        # Notificar enfermeiro sobre associação
        try:
            _notificar_profissional_associacao(db, usuario_enfermeiro_id_para_salvar, paciente_id, "enfermeiro")
        except Exception as e:
            logger.error(f"Erro ao notificar enfermeiro sobre associação: {e}")

    criar_log_auditoria(db, autor_uid=autor_uid, negocio_id=negocio_id, acao=acao_log, detalhes=detalhes_log)
    
    doc = paciente_ref.get()
    if doc.exists:
        data = doc.to_dict()
        data['id'] = doc.id
        
        # Descriptografa campos sensíveis do paciente
        if 'nome' in data and data['nome']:
            try:
                data['nome'] = decrypt_data(data['nome'])
            except Exception as e:
                logger.error(f"Erro ao descriptografar nome do paciente {doc.id}: {e}")
                data['nome'] = "[Erro na descriptografia]"
        
        if 'telefone' in data and data['telefone']:
            try:
                data['telefone'] = decrypt_data(data['telefone'])
            except Exception as e:
                logger.error(f"Erro ao descriptografar telefone do paciente {doc.id}: {e}")
                data['telefone'] = "[Erro na descriptografia]"
        
        if 'endereco' in data and data['endereco']:
            endereco_descriptografado = {}
            for key, value in data['endereco'].items():
                if value and isinstance(value, str) and value.strip():
                    try:
                        endereco_descriptografado[key] = decrypt_data(value)
                    except Exception as e:
                        logger.error(f"Erro ao descriptografar campo de endereço {key} do paciente {doc.id}: {e}")
                        endereco_descriptografado[key] = "[Erro na descriptografia]"
                else:
                    endereco_descriptografado[key] = value
            data['endereco'] = endereco_descriptografado
        
        return data
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

def vincular_paciente_medico(db: firestore.client, negocio_id: str, paciente_id: str, medico_id: Optional[str], autor_uid: str) -> Optional[Dict]:
    """Vincula ou desvincula um paciente de um médico."""
    paciente_ref = db.collection('usuarios').document(paciente_id)

    # Obter médico atual antes da atualização
    paciente_doc_atual = paciente_ref.get()
    medico_atual_id = paciente_doc_atual.to_dict().get('medico_vinculado_id') if paciente_doc_atual.exists else None

    # LÓGICA DE DESVINCULAÇÃO
    if medico_id is None:
        # --- CORREÇÃO APLICADA AQUI ---
        paciente_ref.update({'medico_vinculado_id': firestore.DELETE_FIELD})

        # CORREÇÃO: Remover paciente da lista do médico anterior
        if medico_atual_id:
            try:
                medico_ref = db.collection('usuarios').document(medico_atual_id)
                medico_ref.update({
                    'pacientes_ids': firestore.ArrayRemove([paciente_id])
                })
                logger.info(f"Paciente {paciente_id} removido da lista do médico {medico_atual_id}")
            except Exception as e:
                logger.error(f"Erro ao remover paciente {paciente_id} do médico {medico_atual_id}: {e}")

        acao_log = "DESVINCULO_PACIENTE_MEDICO"
        detalhes_log = {"paciente_id": paciente_id}
        logger.info(f"Paciente {paciente_id} desvinculado do médico.")
    # LÓGICA DE VINCULAÇÃO
    else:
        # (A lógica de validação do médico permanece a mesma)
        medico_doc = db.collection('usuarios').document(medico_id).get()
        if not medico_doc.exists:
            raise ValueError(f"Médico com ID {medico_id} não encontrado.")

        medico_data = medico_doc.to_dict()
        roles = medico_data.get('roles', {})

        if roles.get(negocio_id) != 'medico':
            raise ValueError(f"Usuário {medico_id} não possui a role 'medico' no negócio {negocio_id}.")

        # --- CORREÇÃO APLICADA AQUI ---
        paciente_ref.update({'medico_vinculado_id': medico_id})

        # CORREÇÃO: Remover paciente do médico anterior (se existir)
        if medico_atual_id and medico_atual_id != medico_id:
            try:
                medico_anterior_ref = db.collection('usuarios').document(medico_atual_id)
                medico_anterior_ref.update({
                    'pacientes_ids': firestore.ArrayRemove([paciente_id])
                })
                logger.info(f"Paciente {paciente_id} removido da lista do médico anterior {medico_atual_id}")
            except Exception as e:
                logger.error(f"Erro ao remover paciente {paciente_id} do médico anterior {medico_atual_id}: {e}")

        # CORREÇÃO: Adicionar paciente à lista do novo médico
        try:
            medico_ref = db.collection('usuarios').document(medico_id)
            medico_ref.update({
                'pacientes_ids': firestore.ArrayUnion([paciente_id])
            })
            logger.info(f"Paciente {paciente_id} adicionado à lista do médico {medico_id}")
        except Exception as e:
            logger.error(f"Erro ao adicionar paciente {paciente_id} ao médico {medico_id}: {e}")

        acao_log = "VINCULO_PACIENTE_MEDICO"
        detalhes_log = {"paciente_id": paciente_id, "medico_id": medico_id}
        logger.info(f"Paciente {paciente_id} vinculado ao médico {medico_id}.")

    criar_log_auditoria(db, autor_uid=autor_uid, negocio_id=negocio_id, acao=acao_log, detalhes=detalhes_log)
    
    doc = paciente_ref.get()
    if doc.exists:
        firebase_uid = doc.to_dict().get('firebase_uid')
        if firebase_uid:
            return buscar_usuario_por_firebase_uid(db, firebase_uid)
        else:
            data = doc.to_dict()
            data['id'] = doc.id
            return data
    return None

# Em crud.py, substitua esta função inteira

def vincular_tecnicos_paciente(db: firestore.client, paciente_id: str, tecnicos_ids: List[str], autor_uid: str) -> Optional[Dict]:
    """
    Vincula uma lista de técnicos a um paciente.
    O campo `tecnicos_ids` no documento do paciente será substituído pela lista fornecida.
    """
    try:
        paciente_ref = db.collection('usuarios').document(paciente_id)
        
        # Obter lista atual de técnicos antes da atualização
        paciente_doc_atual = paciente_ref.get()
        tecnicos_atuais = paciente_doc_atual.to_dict().get('tecnicos_ids', []) if paciente_doc_atual.exists else []
        
        # Validar se os IDs dos técnicos existem
        for tecnico_id in tecnicos_ids:
            tecnico_doc = db.collection('usuarios').document(tecnico_id).get()
            if not tecnico_doc.exists:
                raise ValueError(f"Técnico com ID '{tecnico_id}' não encontrado.")
            # Opcional: validar se o papel do usuário é realmente 'tecnico'
        
        # Atualizar o documento do paciente com a lista de técnicos
        paciente_ref.update({
            'tecnicos_ids': tecnicos_ids
        })

        # CORREÇÃO: Atualizar bidirecionalmente - adicionar paciente às listas dos técnicos
        tecnicos_removidos = [t_id for t_id in tecnicos_atuais if t_id not in tecnicos_ids]
        tecnicos_adicionados = [t_id for t_id in tecnicos_ids if t_id not in tecnicos_atuais]

        # Remover paciente dos técnicos que foram desvinculados
        for tecnico_id in tecnicos_removidos:
            try:
                tecnico_ref = db.collection('usuarios').document(tecnico_id)
                tecnico_ref.update({
                    'pacientes_ids': firestore.ArrayRemove([paciente_id])
                })
                logger.info(f"Paciente {paciente_id} removido da lista do técnico {tecnico_id}")
            except Exception as e:
                logger.error(f"Erro ao remover paciente {paciente_id} do técnico {tecnico_id}: {e}")

        # Adicionar paciente aos técnicos que foram vinculados
        for tecnico_id in tecnicos_adicionados:
            try:
                tecnico_ref = db.collection('usuarios').document(tecnico_id)
                tecnico_ref.update({
                    'pacientes_ids': firestore.ArrayUnion([paciente_id])
                })
                logger.info(f"Paciente {paciente_id} adicionado à lista do técnico {tecnico_id}")
            except Exception as e:
                logger.error(f"Erro ao adicionar paciente {paciente_id} ao técnico {tecnico_id}: {e}")

        # Identificar novos técnicos (que não estavam na lista anterior)
        novos_tecnicos = tecnicos_adicionados
        
        # Notificar apenas os novos técnicos
        for novo_tecnico_id in novos_tecnicos:
            try:
                _notificar_profissional_associacao(db, novo_tecnico_id, paciente_id, "tecnico")
            except Exception as e:
                logger.error(f"Erro ao notificar técnico {novo_tecnico_id} sobre associação: {e}")

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

def vincular_supervisor_tecnico(db: firestore.client, tecnico_id: str, supervisor_id: Optional[str], autor_uid: str) -> Optional[Dict]:
    """Vincula ou desvincula um supervisor de um técnico."""
    tecnico_ref = db.collection('usuarios').document(tecnico_id)
    tecnico_doc = tecnico_ref.get()
    if not tecnico_doc.exists: return None

    # LÓGICA DE DESVINCULAÇÃO
    if supervisor_id is None:
        tecnico_ref.update({'supervisor_id': firestore.DELETE_FIELD})
        acao_log = "DESVINCULO_SUPERVISOR_TECNICO"
        detalhes_log = {"tecnico_id": tecnico_id}
        logger.info(f"Supervisor desvinculado do técnico {tecnico_id}.")
    # LÓGICA DE VINCULAÇÃO (existente)
    else:
        supervisor_ref = db.collection('usuarios').document(supervisor_id)
        if not supervisor_ref.get().exists: raise ValueError("Supervisor não encontrado.")
        tecnico_ref.update({'supervisor_id': supervisor_id})
        acao_log = "VINCULO_SUPERVISOR_TECNICO"
        detalhes_log = {"tecnico_id": tecnico_id, "supervisor_id": supervisor_id}
        logger.info(f"Supervisor {supervisor_id} vinculado ao técnico {tecnico_id}.")
    
    negocio_id = list(tecnico_doc.to_dict().get('roles', {}).keys())[0]
    criar_log_auditoria(db, autor_uid=autor_uid, negocio_id=negocio_id, acao=acao_log, detalhes=detalhes_log)

    doc = tecnico_ref.get()
    if doc.exists:
        data = doc.to_dict()
        data['id'] = doc.id
        
        # Descriptografa campos sensíveis do técnico
        if 'nome' in data and data['nome']:
            try:
                data['nome'] = decrypt_data(data['nome'])
            except Exception as e:
                logger.error(f"Erro ao descriptografar nome do técnico {doc.id}: {e}")
                data['nome'] = "[Erro na descriptografia]"
        
        if 'telefone' in data and data['telefone']:
            try:
                data['telefone'] = decrypt_data(data['telefone'])
            except Exception as e:
                logger.error(f"Erro ao descriptografar telefone do técnico {doc.id}: {e}")
                data['telefone'] = "[Erro na descriptografia]"
        
        if 'endereco' in data and data['endereco']:
            endereco_descriptografado = {}
            for key, value in data['endereco'].items():
                if value and isinstance(value, str) and value.strip():
                    try:
                        endereco_descriptografado[key] = decrypt_data(value)
                    except Exception as e:
                        logger.error(f"Erro ao descriptografar campo de endereço {key} do técnico {doc.id}: {e}")
                        endereco_descriptografado[key] = "[Erro na descriptografia]"
                else:
                    endereco_descriptografado[key] = value
            data['endereco'] = endereco_descriptografado
        
        return data
    return None

# Em crud.py, SUBSTITUA a função inteira por esta:

# Em crud.py, SUBSTITUA esta função inteira:

def listar_pacientes_por_profissional_ou_tecnico(db: firestore.client, negocio_id: str, usuario_id: str, role: str) -> List[Dict]:
    """
    Lista todos os pacientes ATIVOS.
    - Se a role for 'admin', retorna TODOS os pacientes do negócio.
    - Se a role for 'profissional' ou 'tecnico', retorna apenas os pacientes vinculados.
    """
    pacientes = []
    try:
        query = db.collection('usuarios').where(f'roles.{negocio_id}', '==', 'cliente')
        
        # ***** A CORREÇÃO ESTÁ AQUI *****
        # Adiciona a lógica para o gestor ('admin')
        if role == 'admin':
            # Se for admin, não aplica filtro de vínculo, pega todos os clientes do negócio.
            pass
        elif role == 'profissional':
            query = query.where('enfermeiro_id', '==', usuario_id)
        elif role == 'tecnico':
            query = query.where('tecnicos_ids', 'array_contains', usuario_id)
        else:
            return []

        for doc in query.stream():
            paciente_data = doc.to_dict()
            status_no_negocio = paciente_data.get('status_por_negocio', {}).get(negocio_id, 'ativo')
            
            if status_no_negocio == 'ativo':
                paciente_data['id'] = doc.id
                
                # Descriptografa campos sensíveis do paciente
                if 'nome' in paciente_data and paciente_data['nome']:
                    try:
                        paciente_data['nome'] = decrypt_data(paciente_data['nome'])
                    except Exception as e:
                        logger.error(f"Erro ao descriptografar nome do paciente {doc.id}: {e}")
                        paciente_data['nome'] = "[Erro na descriptografia]"
                
                if 'telefone' in paciente_data and paciente_data['telefone']:
                    try:
                        paciente_data['telefone'] = decrypt_data(paciente_data['telefone'])
                    except Exception as e:
                        logger.error(f"Erro ao descriptografar telefone do paciente {doc.id}: {e}")
                        paciente_data['telefone'] = "[Erro na descriptografia]"
                
                if 'endereco' in paciente_data and paciente_data['endereco']:
                    endereco_descriptografado = {}
                    for key, value in paciente_data['endereco'].items():
                        if value and isinstance(value, str) and value.strip():
                            try:
                                endereco_descriptografado[key] = decrypt_data(value)
                            except Exception as e:
                                logger.error(f"Erro ao descriptografar campo de endereço {key} do paciente {doc.id}: {e}")
                                endereco_descriptografado[key] = "[Erro na descriptografia]"
                        else:
                            endereco_descriptografado[key] = value
                    paciente_data['endereco'] = endereco_descriptografado
                
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
    
    # Notificar técnicos sobre novo plano de cuidado
    try:
        _notificar_tecnicos_plano_atualizado(db, consulta_data.paciente_id, consulta_dict['id'])
    except Exception as e:
        logger.error(f"Erro ao notificar técnicos sobre novo plano para paciente {consulta_data.paciente_id}: {e}")
    
    return consulta_dict

def adicionar_exame(db: firestore.client, exame_data: schemas.ExameBase, criador_uid: str) -> Dict:
    """Salva um novo exame, adicionando os campos de auditoria."""
    exame_dict = exame_data.model_dump(mode='json')
    now = datetime.utcnow()
    
    exame_dict['criado_por'] = criador_uid
    exame_dict['data_criacao'] = now
    exame_dict['data_atualizacao'] = now
    
    paciente_ref = db.collection('usuarios').document(exame_data.paciente_id)
    doc_ref = paciente_ref.collection('exames').document()
    doc_ref.set(exame_dict)
    
    exame_dict['id'] = doc_ref.id

    # NOVA LINHA: Notificar paciente sobre o exame criado
    _notificar_paciente_exame_criado(db, exame_data.paciente_id, exame_dict)

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
    Lista os técnicos vinculados a um paciente que são supervisionados pelo enfermeiro logado.
    """
    try:
        # 1. Busca os dados do paciente para obter a lista de IDs de técnicos vinculados.
        paciente_doc = db.collection('usuarios').document(paciente_id).get()
        if not paciente_doc.exists:
            logger.warning(f"Paciente com ID {paciente_id} não encontrado.")
            return []
            
        paciente_data = paciente_doc.to_dict()
        tecnicos_vinculados_ids = paciente_data.get('tecnicos_ids', [])
        
        if not tecnicos_vinculados_ids:
            logger.info(f"Paciente {paciente_id} não possui técnicos vinculados.")
            return []

        tecnicos_finais = []
        # 2. Itera sobre os técnicos vinculados e verifica a supervisão de cada um.
        for tecnico_id in tecnicos_vinculados_ids:
            tecnico_doc = db.collection('usuarios').document(tecnico_id).get()
            if not tecnico_doc.exists:
                continue # Pula para o próximo se o técnico não for encontrado

            tecnico_data = tecnico_doc.to_dict()
            # 3. Se o supervisor_id do técnico bate com o ID do enfermeiro, adiciona à lista.
            if tecnico_data.get('supervisor_id') == enfermeiro_id:
                # Descriptografa o nome do técnico
                nome_tecnico = tecnico_data.get('nome', 'Nome não disponível')
                if nome_tecnico and nome_tecnico != 'Nome não disponível':
                    try:
                        nome_tecnico = decrypt_data(nome_tecnico)
                    except Exception as e:
                        logger.error(f"Erro ao descriptografar nome do técnico {tecnico_doc.id}: {e}")
                        nome_tecnico = "[Erro na descriptografia]"
                
                tecnicos_finais.append({
                    "id": tecnico_doc.id,
                    "nome": nome_tecnico,
                    "email": tecnico_data.get('email', 'Email não disponível')
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
        
        # Tentar primeiro ordenar por created_at (consultas mais recentes)
        try:
            query = col.order_by('created_at', direction=firestore.Query.DESCENDING)
            for doc in query.stream():
                consulta_data = doc.to_dict()
                consulta_data['id'] = doc.id
                consultas.append(consulta_data)
        except Exception as created_at_error:
            logger.warning(f"Não foi possível ordenar por created_at: {created_at_error}")
            
        # Se não conseguiu usar created_at ou não tem resultados, usar fallback
        if not consultas:
            try:
                query2 = col.order_by('__name__', direction=firestore.Query.DESCENDING)
                for doc in query2.stream():
                    consulta_data = doc.to_dict()
                    consulta_data['id'] = doc.id
                    consultas.append(consulta_data)
            except Exception as name_error:
                logger.warning(f"Não foi possível ordenar por __name__: {name_error}")
                
                # Último fallback: sem ordenação
                for doc in col.stream():
                    consulta_data = doc.to_dict()
                    consulta_data['id'] = doc.id
                    consultas.append(consulta_data)
                
                # Ordenar em Python se necessário
                consultas.sort(key=lambda x: x.get('created_at', x.get('id', '')), reverse=True)
                
    except Exception as e:
        logger.error(f"Erro ao listar consultas do paciente {paciente_id}: {e}")
    return consultas

def listar_exames(db: firestore.client, paciente_id: str) -> List[Dict]:
    """Lista todos os exames de um paciente, independente do plano de cuidado."""
    exames = []
    try:
        # A query agora busca diretamente na subcoleção do paciente, sem filtro de consulta
        query = db.collection('usuarios').document(paciente_id).collection('exames').order_by('data_exame', direction=firestore.Query.DESCENDING)
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


def _dedup_checklist_items(itens: List[Dict]) -> List[Dict]:
    """Remove duplicatas do checklist usando uma chave normalizada (descricao/descricao_item).
    Mantém a ordem de aparição (estável)."""
    vistos = set()
    resultado = []
    for it in itens or []:
        desc = (it.get('descricao_item') or it.get('descricao') or '').strip().lower()
        chave = desc if desc else f"__id__:{it.get('id','')}"
        if chave in vistos:
            continue
        vistos.add(chave)
        resultado.append(it)
    return resultado

def get_ficha_completa_paciente(db: firestore.client, paciente_id: str, consulta_id: Optional[str] = None) -> Dict:
    """
    Retorna um dicionário com os dados da ficha do paciente,
    filtrando para mostrar apenas o "Plano Ativo" (o mais recente).
    """
    # 1. Encontra a última consulta do paciente.
    consultas = listar_consultas(db, paciente_id)
    
    # Se um consulta_id específico for informado, usa ele.
    if consulta_id:
        ultima_consulta_id = consulta_id
    else:
        # Se não, OBRIGATORIAMENTE usa o ID da mais recente.
        if not consultas:
            # Se não há consultas, retorna tudo vazio.
            return {
                "consultas": [], "medicacoes": [],
                "checklist": [], "orientacoes": [],
            }
        # 2. Pega o ID da última consulta (a primeira da lista ordenada).
        ultima_consulta_id = consultas[0]['id']

    # 3. Usa o ID da última consulta para buscar todos os itens relacionados.
    ficha = {
        "consultas": consultas,
        "medicacoes": listar_medicacoes(db, paciente_id, consulta_id=ultima_consulta_id),
        "checklist": listar_checklist(db, paciente_id, consulta_id=ultima_consulta_id),
        "orientacoes": listar_orientacoes(db, paciente_id, consulta_id=ultima_consulta_id),
    }
    
    # Garante que o checklist não tenha itens duplicados.
    ficha['checklist'] = _dedup_checklist_items(ficha.get('checklist', []))
    return ficha

def listar_prontuarios(db: firestore.client, paciente_id: str) -> List[Dict]:
    """Lista os prontuários simples de um paciente."""
    try:
        coll_ref = db.collection('usuarios').document(paciente_id).collection('prontuarios')
        docs = coll_ref.order_by('data', direction=firestore.Query.DESCENDING).stream()

        prontuarios = []
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            prontuarios.append(data)

        return prontuarios
    except Exception as e:
        logger.error(f"Erro ao listar prontuários do paciente {paciente_id}: {e}")
        return []

def criar_prontuario(db: firestore.client, paciente_id: str, texto: str, tecnico_nome: Optional[str] = None) -> Dict:
    """Cria um novo prontuário para o paciente."""
    try:
        coll_ref = db.collection('usuarios').document(paciente_id).collection('prontuarios')

        prontuario_data = {
            'data': firestore.SERVER_TIMESTAMP,
            'texto': texto,
            'tecnico_nome': tecnico_nome
        }

        doc_ref = coll_ref.add(prontuario_data)[1]

        # Retorna o documento criado
        doc = doc_ref.get()
        data = doc.to_dict()
        data['id'] = doc.id

        logger.info(f"Prontuário criado para paciente {paciente_id}: {doc.id}")
        return data

    except Exception as e:
        logger.error(f"Erro ao criar prontuário para paciente {paciente_id}: {e}")
        raise e

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
def update_exame(
    db: firestore.client, 
    paciente_id: str, 
    exame_id: str, 
    update_data: schemas.ExameUpdate, 
    current_user: schemas.UsuarioProfile, 
    negocio_id: str
) -> Optional[Dict]:
    """Atualiza um exame existente, validando as permissões de edição."""
    exame_ref = db.collection('usuarios').document(paciente_id).collection('exames').document(exame_id)
    exame_doc = exame_ref.get()

    if not exame_doc.exists:
        return None

    exame_atual = exame_doc.to_dict()
    user_role = current_user.roles.get(negocio_id)

    # REGRA DE PERMISSÃO: Admin pode tudo, Enfermeiro só o que ele criou.
    if user_role != 'admin' and exame_atual.get('criado_por') != current_user.firebase_uid:
        raise HTTPException(
            status_code=403, 
            detail="Acesso negado: Enfermeiros só podem editar os exames que criaram."
        )

    update_dict = update_data.model_dump(exclude_unset=True, mode='json')
    update_dict['data_atualizacao'] = datetime.utcnow()
    
    exame_ref.update(update_dict)
    
    updated_doc = exame_ref.get()
    data = updated_doc.to_dict()
    data['id'] = updated_doc.id
    return data

def delete_exame(
    db: firestore.client, 
    paciente_id: str, 
    exame_id: str, 
    current_user: schemas.UsuarioProfile, 
    negocio_id: str
) -> bool:
    """Deleta um exame, validando as permissões de exclusão."""
    exame_ref = db.collection('usuarios').document(paciente_id).collection('exames').document(exame_id)
    exame_doc = exame_ref.get()

    if not exame_doc.exists:
        return False

    exame_atual = exame_doc.to_dict()
    user_role = current_user.roles.get(negocio_id)

    # REGRA DE PERMISSÃO: Admin pode tudo, Enfermeiro só o que ele criou.
    if user_role != 'admin' and exame_atual.get('criado_por') != current_user.firebase_uid:
        raise HTTPException(
            status_code=403, 
            detail="Acesso negado: Enfermeiros só podem deletar os exames que criaram."
        )

    exame_ref.delete()
    return True

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
    """Salva um novo registro do técnico na subcoleção de um paciente, criptografando dados sensíveis."""
    registro_dict = registro_data.model_dump()
    
    # Define campos sensíveis que precisam ser criptografados
    sensitive_fields = ['anotacao_geral', 'medicamentos', 'atividades', 'intercorrencias']
    
    # Criptografa campos sensíveis antes de salvar
    for field in sensitive_fields:
        if field in registro_dict and registro_dict[field] is not None:
            if isinstance(registro_dict[field], str) and registro_dict[field].strip():
                registro_dict[field] = encrypt_data(registro_dict[field])
    
    registro_dict.update({
        "data_ocorrencia": datetime.utcnow(),
        "tecnico_id": tecnico.id,
        "tecnico_nome": tecnico.nome,
    })
    
    paciente_ref = db.collection('usuarios').document(registro_data.paciente_id)
    doc_ref = paciente_ref.collection('diario_tecnico').document()
    doc_ref.set(registro_dict)
    
    registro_dict['id'] = doc_ref.id
    
    # Descriptografa campos sensíveis para a resposta da API
    for field in sensitive_fields:
        if field in registro_dict and registro_dict[field] is not None:
            if isinstance(registro_dict[field], str) and registro_dict[field].strip():
                try:
                    registro_dict[field] = decrypt_data(registro_dict[field])
                except Exception as e:
                    logger.error(f"Erro ao descriptografar campo {field} do registro diário: {e}")
                    registro_dict[field] = "[Erro na descriptografia]"
    
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

        # Define campos sensíveis que precisam ser descriptografados
        sensitive_fields = ['anotacao_geral', 'medicamentos', 'atividades', 'intercorrencias']

        for doc in query.stream():
            registro_data = doc.to_dict()
            registro_data['id'] = doc.id
            
            # Descriptografa campos sensíveis
            for field in sensitive_fields:
                if field in registro_data and registro_data[field] is not None:
                    if isinstance(registro_data[field], str) and registro_data[field].strip():
                        try:
                            registro_data[field] = decrypt_data(registro_data[field])
                        except Exception as e:
                            logger.error(f"Erro ao descriptografar campo {field} do registro diário {doc.id}: {e}")
                            registro_data[field] = "[Erro na descriptografia]"
            
            tecnico_id = registro_data.get('tecnico_id')

            if tecnico_id:
                if tecnico_id in tecnicos_cache:
                    tecnico_perfil = tecnicos_cache[tecnico_id]
                else:
                    tecnico_doc = db.collection('usuarios').document(tecnico_id).get()
                    if tecnico_doc.exists:
                        tecnico_data = tecnico_doc.to_dict()
                        nome_tecnico = tecnico_data.get('nome')
                        if nome_tecnico:
                            try:
                                nome_tecnico = decrypt_data(nome_tecnico)
                            except Exception as e:
                                logger.error(f"Erro ao descriptografar nome do técnico {tecnico_id}: {e}")
                                nome_tecnico = "[Erro na descriptografia]"
                        
                        tecnico_perfil = {
                            "id": tecnico_doc.id,
                            "nome": nome_tecnico,
                            "email": tecnico_data.get('email')
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

# Substitua as DUAS versões antigas por esta ÚNICA versão correta
def verificar_leitura_plano_do_dia(db: firestore.client, paciente_id: str, tecnico_id: str, data: date) -> dict:
    """
    Verifica se a leitura do plano já foi confirmada hoje e retorna o status e a data.
    """
    data_inicio_dia = datetime.combine(data, datetime.min.time())
    data_fim_dia = datetime.combine(data, datetime.max.time())
    
    query = db.collection('usuarios').document(paciente_id).collection('confirmacoes_leitura')\
        .where('usuario_id', '==', tecnico_id)\
        .where('data_confirmacao', '>=', data_inicio_dia)\
        .where('data_confirmacao', '<=', data_fim_dia)\
        .order_by('data_confirmacao', direction=firestore.Query.DESCENDING)\
        .limit(1)
        
    docs = list(query.stream())
    
    if not docs:
        return {
            "leitura_confirmada": False,
            "ultima_leitura": None
        }
    
    ultima_leitura_doc = docs[0].to_dict()
    data_confirmacao = ultima_leitura_doc.get("data_confirmacao")
    
    return {
        "leitura_confirmada": True,
        "ultima_leitura": data_confirmacao.isoformat() if data_confirmacao else None
    }

def listar_checklist_diario_com_replicacao(db: firestore.client, paciente_id: str, dia: date, negocio_id: str) -> List[Dict]:
    """Busca o checklist do dia. Se não existir, replica o do dia anterior de forma segura."""
    try:
        start_dt = datetime.combine(dia, time.min)
        end_dt = datetime.combine(dia, time.max)
        col_ref = db.collection('usuarios').document(paciente_id).collection('checklist')
        
        # 1. Tenta buscar o checklist de hoje
        query_hoje = col_ref.where('negocio_id', '==', negocio_id).where('data_criacao', '>=', start_dt).where('data_criacao', '<=', end_dt)
        docs_hoje = list(query_hoje.stream())

        if docs_hoje:
            return [{'id': doc.id, 'descricao': doc.to_dict().get('descricao_item', ''), 'concluido': doc.to_dict().get('concluido', False)} for doc in docs_hoje]

        # 2. Se não encontrou, busca a data do último checklist disponível
        query_ultimo_dia = col_ref.where('negocio_id', '==', negocio_id).where('data_criacao', '<', start_dt).order_by('data_criacao', direction=firestore.Query.DESCENDING).limit(1)
        docs_anteriores = list(query_ultimo_dia.stream())
        
        if not docs_anteriores:
            logger.info(f"Nenhum checklist encontrado para hoje ou dias anteriores para o paciente {paciente_id}.")
            return []

        # 3. Pega a data do último checklist e busca todos os itens daquele dia
        ultimo_doc_data = docs_anteriores[0].to_dict()['data_criacao'].date()
        start_anterior = datetime.combine(ultimo_doc_data, time.min)
        end_anterior = datetime.combine(ultimo_doc_data, time.max)
        
        query_para_replicar = col_ref.where('negocio_id', '==', negocio_id).where('data_criacao', '>=', start_anterior).where('data_criacao', '<=', end_anterior)
        docs_para_replicar = list(query_para_replicar.stream())

        if not docs_para_replicar:
            return []

        # 4. Cria os novos itens em batch
        batch = db.batch()
        novos_itens_resposta = []
        for doc in docs_para_replicar:
            dados_antigos = doc.to_dict()
            novos_dados = {
                "paciente_id": paciente_id, "negocio_id": negocio_id,
                "descricao_item": dados_antigos.get("descricao_item", "Item sem descrição"),
                "concluido": False,
                "data_criacao": datetime.combine(dia, datetime.utcnow().time()), # Usa a data de hoje
                "consulta_id": dados_antigos.get("consulta_id")
            }
            novo_doc_ref = col_ref.document()
            batch.set(novo_doc_ref, novos_dados)
            novos_itens_resposta.append({'id': novo_doc_ref.id, 'descricao': novos_dados['descricao_item'], 'concluido': novos_dados['concluido']})
        
        batch.commit()
        logger.info(f"Checklist replicado com {len(novos_itens_resposta)} itens para o paciente {paciente_id} no dia {dia.isoformat()}.")
        return novos_itens_resposta

    except Exception as e:
        # Captura qualquer erro inesperado e evita o 500, retornando uma lista vazia e logando o problema.
        logger.error(f"ERRO CRÍTICO ao listar/replicar checklist para paciente {paciente_id}: {e}")
        # É importante levantar uma exceção aqui para que o FastAPI retorne uma resposta de erro adequada em vez de travar
        raise HTTPException(status_code=500, detail=f"Erro interno ao processar o checklist: {e}")

def atualizar_item_checklist_diario(db: firestore.client, paciente_id: str, item_id: str, update_data: schemas.ChecklistItemDiarioUpdate) -> Optional[Dict]:
    """Permite ao técnico marcar os itens ao longo do dia."""
    item_ref = db.collection('usuarios').document(paciente_id).collection('checklist').document(item_id)
    if not item_ref.get().exists: return None
    item_ref.update(update_data.model_dump())
    updated_doc = item_ref.get().to_dict()
    
    # Se o item foi marcado como concluído, verificar se checklist está 100% completo
    if update_data.concluido:
        try:
            _verificar_checklist_completo(db, paciente_id, item_id)
        except Exception as e:
            logger.error(f"Erro ao verificar checklist completo: {e}")
    
    return {'id': item_id, 'descricao': updated_doc.get('descricao_item', ''), 'concluido': updated_doc.get('concluido', False)}


# Em crud.py, substitua a função inteira por esta:

# Em crud.py, SUBSTITUA a função inteira por esta:

def get_checklist_diario_plano_ativo(db: firestore.client, paciente_id: str, dia: date, negocio_id: str) -> List[Dict]:
    """
    Busca o checklist do dia com a lógica corrigida.
    1. Encontra o plano de cuidado (consulta) que estava ativo NA DATA solicitada.
    2. Se nenhum plano existia naquela data, retorna [].
    3. Se um plano existia, busca o checklist daquela data.
    4. A replicação de um novo checklist só ocorre se a data solicitada for HOJE.
    5. CORREÇÃO: Garante que a lista final não tenha itens duplicados.
    """
    try:
        # 1. Encontrar o plano de cuidado (consulta) válido para a data solicitada.
        end_of_day = datetime.combine(dia, time.max)
        consulta_ref = db.collection('usuarios').document(paciente_id).collection('consultas')
        query_plano_valido = consulta_ref.where('created_at', '<=', end_of_day)\
                                         .order_by('created_at', direction=firestore.Query.DESCENDING)\
                                         .limit(1)
        
        docs_plano_valido = list(query_plano_valido.stream())

        if not docs_plano_valido:
            logger.info(f"Nenhum plano de cuidado ativo para {paciente_id} em {dia.isoformat()}.")
            return []
            
        plano_valido_id = docs_plano_valido[0].id
        logger.info(f"Plano válido para {dia.isoformat()} é a consulta {plano_valido_id}.")

        checklist_template = listar_checklist(db, paciente_id, plano_valido_id)
        if not checklist_template:
            logger.info(f"Plano {plano_valido_id} não possui checklist.")
            return []

        col_ref = db.collection('usuarios').document(paciente_id).collection('checklist')
        start_dt = datetime.combine(dia, time.min)
        end_dt = datetime.combine(dia, time.max)
        
        query_checklist_do_dia = col_ref.where('negocio_id', '==', negocio_id)\
                                        .where('data_criacao', '>=', start_dt)\
                                        .where('data_criacao', '<=', end_dt)\
                                        .where('consulta_id', '==', plano_valido_id)
        
        docs_checklist_do_dia = list(query_checklist_do_dia.stream())

        # Se não encontrou e a data for HOJE, replica o checklist.
        if not docs_checklist_do_dia and dia == date.today():
            logger.info(f"Replicando {len(checklist_template)} itens do plano {plano_valido_id} para hoje.")
            batch = db.batch()
            for item_template in checklist_template:
                novo_doc_ref = col_ref.document()
                batch.set(novo_doc_ref, {
                    "paciente_id": paciente_id, "negocio_id": negocio_id,
                    "descricao_item": item_template.get("descricao_item", "Item sem descrição"),
                    "concluido": False,
                    "data_criacao": datetime.combine(dia, datetime.utcnow().time()),
                    "consulta_id": plano_valido_id
                })
            batch.commit()
            # Após a replicação, busca novamente para obter os IDs corretos
            docs_checklist_do_dia = list(query_checklist_do_dia.stream())

        # --- INÍCIO DA CORREÇÃO CONTRA DUPLICATAS ---
        itens_formatados = []
        descricoes_vistas = set()
        for doc in docs_checklist_do_dia:
            item_data = doc.to_dict()
            descricao = item_data.get('descricao_item', '')
            if descricao not in descricoes_vistas:
                itens_formatados.append({
                    'id': doc.id,
                    'descricao': descricao,
                    'concluido': item_data.get('concluido', False)
                })
                descricoes_vistas.add(descricao)
        # --- FIM DA CORREÇÃO ---

        logger.info(f"Retornando {len(itens_formatados)} itens de checklist únicos para o dia {dia.isoformat()}.")
        return itens_formatados

    except Exception as e:
        logger.error(f"ERRO CRÍTICO ao buscar checklist do plano ativo para o paciente {paciente_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno ao processar o checklist: {e}")
    
# =================================================================================
# FUNÇÕES DE REGISTROS DIÁRIOS ESTRUTURADOS
# =================================================================================

# def criar_registro_diario_estruturado(db: firestore.client, registro_data: schemas.RegistroDiarioCreate, tecnico_id: str) -> Dict:
#     """
#     Adiciona um novo registro estruturado ao diário de acompanhamento de um paciente.
#     Agora valida que 'conteudo' é compatível com o 'tipo' informado; caso contrário, retorna 422.
#     """
#     # Revalida o conteudo de acordo com o tipo escolhido (para evitar documentos corrompidos)
#     try:
#         tipo = registro_data.tipo
#         bruto = registro_data.conteudo if isinstance(registro_data.conteudo, dict) else registro_data.conteudo.model_dump()
#         if tipo == 'sinais_vitais':
#             conteudo_ok = schemas.SinaisVitaisConteudo.model_validate(bruto)
#         elif tipo == 'medicacao':
#             conteudo_ok = schemas.MedicacaoConteudo.model_validate(bruto)
#         elif tipo == 'atividade':
#             conteudo_ok = schemas.AtividadeConteudo.model_validate(bruto)
#         elif tipo == 'anotacao':
#             conteudo_ok = schemas.AnotacaoConteudo.model_validate(bruto)
#         elif tipo == 'intercorrencia':
#             conteudo_ok = schemas.IntercorrenciaConteudo.model_validate(bruto)
#         else:
#             raise ValueError(f"Tipo de registro desconhecido: {tipo}")
#     except Exception as e:
#         raise HTTPException(status_code=422, detail=f"Conteúdo incompatível com o tipo '{registro_data.tipo}': {e}")

#     # Monta o dicionário para salvar no Firestore
#     registro_dict_para_salvar = {
#         "negocio_id": registro_data.negocio_id,
#         "paciente_id": registro_data.paciente_id,
#         "tipo": tipo,
#         "conteudo": conteudo_ok.model_dump(),
#         "tecnico_id": tecnico_id,
#         "data_registro": datetime.utcnow(),
#     }

#     # Salva o documento no banco de dados
#     paciente_ref = db.collection('usuarios').document(registro_data.paciente_id)
#     doc_ref = paciente_ref.collection('registros_diarios_estruturados').document()
#     doc_ref.set(registro_dict_para_salvar)

#     # Monta o técnico (objeto reduzido)
#     tecnico_doc = db.collection('usuarios').document(tecnico_id).get()
#     if tecnico_doc.exists:
#         tdat = tecnico_doc.to_dict() or {}
#         tecnico_perfil = {
#             "id": tecnico_doc.id,
#             "nome": tdat.get('nome', 'Nome não disponível'),
#             "email": tdat.get('email', 'Email não disponível'),
#         }
#     else:
#         tecnico_perfil = {"id": tecnico_id, "nome": "Técnico Desconhecido", "email": ""}

#     resposta_dict = registro_dict_para_salvar.copy()
#     resposta_dict['id'] = doc_ref.id
#     resposta_dict['tecnico'] = tecnico_perfil
#     return resposta_dict

# Em crud.py, substitua a função inteira por esta:

# Em crud.py, substitua esta função

def criar_registro_diario_estruturado(db: firestore.client, registro_data: schemas.RegistroDiarioCreate, tecnico_id: str) -> Dict:
    """
    Adiciona um novo registro estruturado ao diário de acompanhamento de um paciente, criptografando dados sensíveis e notificando o enfermeiro.
    """
    try:
        conteudo_ok = registro_data.conteudo
        conteudo_dict = conteudo_ok.model_dump()
        
        if 'descricao' in conteudo_dict and conteudo_dict['descricao']:
            conteudo_dict['descricao'] = encrypt_data(conteudo_dict['descricao'])

        registro_dict_para_salvar = {
            "negocio_id": registro_data.negocio_id,
            "paciente_id": registro_data.paciente_id,
            "tipo": registro_data.tipo,
            "conteudo": conteudo_dict,
            "tecnico_id": tecnico_id,
            "data_registro": registro_data.data_hora,
        }

        paciente_ref = db.collection('usuarios').document(registro_data.paciente_id)
        doc_ref = paciente_ref.collection('registros_diarios_estruturados').document()
        doc_ref.set(registro_dict_para_salvar)

        # Prepara a resposta da API
        resposta_dict = registro_dict_para_salvar.copy()
        resposta_dict['id'] = doc_ref.id
        
        tecnico_doc = db.collection('usuarios').document(tecnico_id).get()
        if tecnico_doc.exists:
            tdat = tecnico_doc.to_dict() or {}
            resposta_dict['tecnico'] = {
                "id": tecnico_doc.id,
                "nome": decrypt_data(tdat.get('nome', '')) if tdat.get('nome') else 'Técnico',
                "email": tdat.get('email', ''),
            }
        else:
            resposta_dict['tecnico'] = {"id": tecnico_id, "nome": "Técnico Desconhecido", "email": ""}
        
        if 'descricao' in conteudo_dict and conteudo_dict['descricao']:
             resposta_dict['conteudo']['descricao'] = decrypt_data(conteudo_dict['descricao'])
        
        # --- INÍCIO DA ALTERAÇÃO ---
        # 5. Notificar o enfermeiro responsável
        try:
            # Passamos o dicionário já com o ID para a função de notificação
            _notificar_enfermeiro_novo_registro_diario(db, resposta_dict)
        except Exception as e:
            logger.error(f"Falha ao disparar notificação para novo registro diário {doc_ref.id}: {e}")
        # --- FIM DA ALTERAÇÃO ---

        return resposta_dict

    except Exception as e:
        logger.error(f"Erro inesperado ao criar registro diário estruturado: {e}")
        raise HTTPException(status_code=500, detail=f"Ocorreu um erro interno no servidor: {e}")
    

def listar_registros_diario_estruturado(
    db: firestore.client,
    paciente_id: str,
    data: Optional[date] = None,
    tipo: Optional[str] = None
) -> List[schemas.RegistroDiarioResponse]:
    """
    Lista os registros diários estruturados de um paciente.
    AGORA CORRIGIDO: Lida de forma robusta com registros antigos (estruturados)
    e novos (texto livre), sem depender de schemas que foram removidos,
    convertendo todos para o formato de anotação simples.
    """
    registros_pydantic: List[schemas.RegistroDiarioResponse] = []
    try:
        coll_ref = db.collection('usuarios').document(paciente_id).collection('registros_diarios_estruturados')
        query = coll_ref.order_by('data_registro', direction=firestore.Query.DESCENDING)

        if tipo:
            query = query.where('tipo', '==', tipo)

        if data:
            inicio = datetime.combine(data, time.min)
            fim = datetime.combine(data, time.max)
            query = query.where('data_registro', '>=', inicio).where('data_registro', '<=', fim)

        docs = list(query.stream())
        tecnicos_cache: Dict[str, Dict] = {}

        for doc in docs:
            d = doc.to_dict() or {}
            d['id'] = doc.id

            conteudo_bruto = d.get('conteudo', {}) or {}
            descricao_final = ""

            # Lógica para converter QUALQUER formato de 'conteudo' para uma 'descricao' simples
            if 'descricao' in conteudo_bruto:
                # Se for um registro novo ou um antigo que já tinha descrição, usa ela
                descricao_final = conteudo_bruto.get('descricao', '')
                
                # Descriptografa a descrição se necessário
                if descricao_final and isinstance(descricao_final, str) and descricao_final.strip():
                    try:
                        descricao_final = decrypt_data(descricao_final)
                    except Exception as e:
                        logger.error(f"Erro ao descriptografar descrição do registro diário estruturado {doc.id}: {e}")
                        descricao_final = "[Erro na descriptografia]"
            else:
                # Se for um registro antigo e estruturado, monta uma descrição a partir dos dados
                partes = []
                if 'pressao_sistolica' in conteudo_bruto:
                    partes.append(f"PA: {conteudo_bruto.get('pressao_sistolica')}/{conteudo_bruto.get('pressao_diastolica')}")
                if 'temperatura' in conteudo_bruto:
                    partes.append(f"Temp: {conteudo_bruto.get('temperatura')}°C")
                if 'batimentos_cardiacos' in conteudo_bruto:
                    partes.append(f"FC: {conteudo_bruto.get('batimentos_cardiacos')} bpm")
                if 'saturacao_oxigenio' in conteudo_bruto:
                    partes.append(f"Sat O²: {conteudo_bruto.get('saturacao_oxigenio')}%")
                if 'nome' in conteudo_bruto: # Para medicação antiga
                    partes.append(f"Medicamento: {conteudo_bruto.get('nome')} ({conteudo_bruto.get('dose')})")
                
                descricao_final = ", ".join(filter(None, partes))
                if not descricao_final:
                    descricao_final = "Registro estruturado antigo sem descrição."

            # Monta o objeto de conteúdo final, que é sempre uma anotação simples
            conteudo_final = schemas.AnotacaoConteudo(descricao=descricao_final)

            # Monta o objeto 'tecnico' (lógica reaproveitada)
            tecnico_id = d.get('tecnico_id')
            tecnico_perfil = None
            if tecnico_id:
                if tecnico_id in tecnicos_cache:
                    tecnico_perfil = tecnicos_cache[tecnico_id]
                else:
                    tdoc = db.collection('usuarios').document(tecnico_id).get()
                    if tdoc.exists:
                        tdat = tdoc.to_dict() or {}
                        nome_tecnico = tdat.get('nome')
                        if nome_tecnico:
                            try:
                                nome_tecnico = decrypt_data(nome_tecnico)
                            except Exception as e:
                                logger.error(f"Erro ao descriptografar nome do técnico {tecnico_id}: {e}")
                                nome_tecnico = "[Erro na descriptografia]"
                        
                        tecnico_perfil = {'id': tdoc.id, 'nome': nome_tecnico, 'email': tdat.get('email')}
                    else:
                        tecnico_perfil = {'id': tecnico_id, 'nome': 'Técnico Desconhecido', 'email': ''}
                    tecnicos_cache[tecnico_id] = tecnico_perfil
            
            # Constrói a resposta final
            registro_data = {
                'id': d['id'],
                'negocio_id': d.get('negocio_id'),
                'paciente_id': d.get('paciente_id'),
                'tecnico': tecnico_perfil or {'id': '', 'nome': '', 'email': ''},
                'data_registro': d.get('data_registro'),
                'tipo': d.get('tipo', 'anotacao'),
                'conteudo': conteudo_final
            }

            try:
                # Valida com o schema de resposta, que agora espera AnotacaoConteudo
                registros_pydantic.append(schemas.RegistroDiarioResponse.model_validate(registro_data))
            except Exception as e:
                logger.error(f"Falha ao montar o modelo de resposta final para o registro {doc.id}: {e}")

    except Exception as e:
        logger.error(f"Erro ao listar registros estruturados para o paciente {paciente_id}: {e}")
        # O erro original acontecia aqui. Agora a exceção é mais genérica.
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

# =================================================================================
# 1. NOVAS FUNÇÕES: FICHA DE ANAMNESE
# =================================================================================

def criar_anamnese(db: firestore.client, paciente_id: str, anamnese_data: schemas.AnamneseCreate) -> Dict:
    """Cria um novo registro de anamnese para um paciente, criptografando dados sensíveis."""
    anamnese_dict = anamnese_data.model_dump(mode='json')
    
    # Define campos sensíveis que precisam ser criptografados
    sensitive_fields = [
        'nome_paciente', 'queixa_principal', 'historico_doenca_atual', 'historia_familiar',
        'sistema_respiratorio', 'sistema_cardiovascular', 'abdome', 'estado_nutricional',
        'eliminacoes_fisiologicas', 'drenos_sondas_cateteres', 'pele_mucosas',
        'apoio_familiar_social', 'necessidades_emocionais_espirituais'
    ]
    
    # Campos sensíveis dentro do objeto antecedentes_pessoais
    antecedentes_sensitive_fields = [
        'outras_doencas_cronicas', 'cirurgias_anteriores', 'alergias', 
        'medicamentos_uso_continuo', 'outros_habitos'
    ]
    
    # Criptografa campos sensíveis antes de salvar
    for field in sensitive_fields:
        if field in anamnese_dict and anamnese_dict[field] is not None:
            if isinstance(anamnese_dict[field], str) and anamnese_dict[field].strip():
                anamnese_dict[field] = encrypt_data(anamnese_dict[field])
    
    # Criptografa campos sensíveis dentro de antecedentes_pessoais
    if 'antecedentes_pessoais' in anamnese_dict and anamnese_dict['antecedentes_pessoais'] is not None:
        for field in antecedentes_sensitive_fields:
            if field in anamnese_dict['antecedentes_pessoais'] and anamnese_dict['antecedentes_pessoais'][field] is not None:
                if isinstance(anamnese_dict['antecedentes_pessoais'][field], str) and anamnese_dict['antecedentes_pessoais'][field].strip():
                    anamnese_dict['antecedentes_pessoais'][field] = encrypt_data(anamnese_dict['antecedentes_pessoais'][field])
    
    anamnese_dict.update({
        "paciente_id": paciente_id,
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": None,
    })
    
    doc_ref = db.collection('usuarios').document(paciente_id).collection('anamneses').document()
    doc_ref.set(anamnese_dict)

    # --- INÍCIO DA CORREÇÃO ---
    # Para a RESPOSTA da API, não podemos retornar o 'SERVER_TIMESTAMP'.
    # Substituímos pelo horário atual do servidor da aplicação, que é válido para o schema.
    anamnese_dict['id'] = doc_ref.id
    anamnese_dict['created_at'] = datetime.utcnow()
    
    # Descriptografa os campos sensíveis para retornar dados legíveis na resposta da API
    for field in sensitive_fields:
        if field in anamnese_dict and anamnese_dict[field] is not None:
            if isinstance(anamnese_dict[field], str) and anamnese_dict[field].strip():
                try:
                    anamnese_dict[field] = decrypt_data(anamnese_dict[field])
                except Exception as e:
                    logger.error(f"Erro ao descriptografar campo {field} da anamnese: {e}")
                    anamnese_dict[field] = "[Erro na descriptografia]"
    
    # Descriptografa campos sensíveis dentro de antecedentes_pessoais
    if 'antecedentes_pessoais' in anamnese_dict and anamnese_dict['antecedentes_pessoais'] is not None:
        for field in antecedentes_sensitive_fields:
            if field in anamnese_dict['antecedentes_pessoais'] and anamnese_dict['antecedentes_pessoais'][field] is not None:
                if isinstance(anamnese_dict['antecedentes_pessoais'][field], str) and anamnese_dict['antecedentes_pessoais'][field].strip():
                    try:
                        anamnese_dict['antecedentes_pessoais'][field] = decrypt_data(anamnese_dict['antecedentes_pessoais'][field])
                    except Exception as e:
                        logger.error(f"Erro ao descriptografar campo {field} dos antecedentes pessoais: {e}")
                        anamnese_dict['antecedentes_pessoais'][field] = "[Erro na descriptografia]"
    # --- FIM DA CORREÇÃO ---
    
    return anamnese_dict

def listar_anamneses_por_paciente(db: firestore.client, paciente_id: str) -> List[Dict]:
    """Lista todas as anamneses de um paciente, descriptografando dados sensíveis."""
    anamneses = []
    query = db.collection('usuarios').document(paciente_id).collection('anamneses').order_by('data_avaliacao', direction=firestore.Query.DESCENDING)
    
    # Define campos sensíveis que precisam ser descriptografados
    sensitive_fields = [
        'nome_paciente', 'queixa_principal', 'historico_doenca_atual', 'historia_familiar',
        'sistema_respiratorio', 'sistema_cardiovascular', 'abdome', 'estado_nutricional',
        'eliminacoes_fisiologicas', 'drenos_sondas_cateteres', 'pele_mucosas',
        'apoio_familiar_social', 'necessidades_emocionais_espirituais'
    ]
    
    # Campos sensíveis dentro do objeto antecedentes_pessoais
    antecedentes_sensitive_fields = [
        'outras_doencas_cronicas', 'cirurgias_anteriores', 'alergias', 
        'medicamentos_uso_continuo', 'outros_habitos'
    ]
    
    for doc in query.stream():
        data = doc.to_dict()
        data['id'] = doc.id
        
        # Descriptografa campos sensíveis
        for field in sensitive_fields:
            if field in data and data[field] is not None:
                if isinstance(data[field], str) and data[field].strip():
                    try:
                        data[field] = decrypt_data(data[field])
                    except Exception as e:
                        logger.error(f"Erro ao descriptografar campo {field} da anamnese {doc.id}: {e}")
                        data[field] = "[Erro na descriptografia]"
        
        # Descriptografa campos sensíveis dentro de antecedentes_pessoais
        if 'antecedentes_pessoais' in data and data['antecedentes_pessoais'] is not None:
            for field in antecedentes_sensitive_fields:
                if field in data['antecedentes_pessoais'] and data['antecedentes_pessoais'][field] is not None:
                    if isinstance(data['antecedentes_pessoais'][field], str) and data['antecedentes_pessoais'][field].strip():
                        try:
                            data['antecedentes_pessoais'][field] = decrypt_data(data['antecedentes_pessoais'][field])
                        except Exception as e:
                            logger.error(f"Erro ao descriptografar campo {field} dos antecedentes pessoais da anamnese {doc.id}: {e}")
                            data['antecedentes_pessoais'][field] = "[Erro na descriptografia]"
        
        anamneses.append(data)
    return anamneses

def atualizar_anamnese(db: firestore.client, anamnese_id: str, paciente_id: str, update_data: schemas.AnamneseUpdate) -> Optional[Dict]:
    """Atualiza uma anamnese existente, criptografando novos dados sensíveis e descriptografando para resposta."""
    anamnese_ref = db.collection('usuarios').document(paciente_id).collection('anamneses').document(anamnese_id)
    if not anamnese_ref.get().exists:
        return None
    
    update_dict = update_data.model_dump(exclude_unset=True, mode='json')
    
    # Define campos sensíveis que precisam ser criptografados
    sensitive_fields = [
        'nome_paciente', 'queixa_principal', 'historico_doenca_atual', 'historia_familiar',
        'sistema_respiratorio', 'sistema_cardiovascular', 'abdome', 'estado_nutricional',
        'eliminacoes_fisiologicas', 'drenos_sondas_cateteres', 'pele_mucosas',
        'apoio_familiar_social', 'necessidades_emocionais_espirituais'
    ]
    
    # Campos sensíveis dentro do objeto antecedentes_pessoais
    antecedentes_sensitive_fields = [
        'outras_doencas_cronicas', 'cirurgias_anteriores', 'alergias', 
        'medicamentos_uso_continuo', 'outros_habitos'
    ]
    
    # Criptografa campos sensíveis que estão sendo atualizados
    for field in sensitive_fields:
        if field in update_dict and update_dict[field] is not None:
            if isinstance(update_dict[field], str) and update_dict[field].strip():
                update_dict[field] = encrypt_data(update_dict[field])
    
    # Criptografa campos sensíveis dentro de antecedentes_pessoais se está sendo atualizado
    if 'antecedentes_pessoais' in update_dict and update_dict['antecedentes_pessoais'] is not None:
        for field in antecedentes_sensitive_fields:
            if field in update_dict['antecedentes_pessoais'] and update_dict['antecedentes_pessoais'][field] is not None:
                if isinstance(update_dict['antecedentes_pessoais'][field], str) and update_dict['antecedentes_pessoais'][field].strip():
                    update_dict['antecedentes_pessoais'][field] = encrypt_data(update_dict['antecedentes_pessoais'][field])
    
    update_dict['updated_at'] = firestore.SERVER_TIMESTAMP
    anamnese_ref.update(update_dict)
    
    updated_doc = anamnese_ref.get()
    data = updated_doc.to_dict()
    data['id'] = updated_doc.id
    
    # Descriptografa campos sensíveis para a resposta da API
    for field in sensitive_fields:
        if field in data and data[field] is not None:
            if isinstance(data[field], str) and data[field].strip():
                try:
                    data[field] = decrypt_data(data[field])
                except Exception as e:
                    logger.error(f"Erro ao descriptografar campo {field} da anamnese {anamnese_id}: {e}")
                    data[field] = "[Erro na descriptografia]"
    
    # Descriptografa campos sensíveis dentro de antecedentes_pessoais para resposta
    if 'antecedentes_pessoais' in data and data['antecedentes_pessoais'] is not None:
        for field in antecedentes_sensitive_fields:
            if field in data['antecedentes_pessoais'] and data['antecedentes_pessoais'][field] is not None:
                if isinstance(data['antecedentes_pessoais'][field], str) and data['antecedentes_pessoais'][field].strip():
                    try:
                        data['antecedentes_pessoais'][field] = decrypt_data(data['antecedentes_pessoais'][field])
                    except Exception as e:
                        logger.error(f"Erro ao descriptografar campo {field} dos antecedentes pessoais da anamnese {anamnese_id}: {e}")
                        data['antecedentes_pessoais'][field] = "[Erro na descriptografia]"
    
    return data

# =================================================================================
# 2. NOVA FUNÇÃO: ENDEREÇO
# =================================================================================

def atualizar_endereco_paciente(db: firestore.client, paciente_id: str, endereco_data: schemas.EnderecoUpdate) -> Optional[Dict]:
    """Atualiza o endereço de um paciente, criptografando dados sensíveis."""
    paciente_ref = db.collection('usuarios').document(paciente_id)
    if not paciente_ref.get().exists:
        return None
    
    # Criptografa os dados do endereço antes de salvar
    endereco_dict = endereco_data.model_dump()
    endereco_criptografado = {}
    for key, value in endereco_dict.items():
        if value is not None and isinstance(value, str) and value.strip():
            endereco_criptografado[key] = encrypt_data(value)
        else:
            endereco_criptografado[key] = value
    
    paciente_ref.update({"endereco": endereco_criptografado})
    updated_doc = paciente_ref.get()
    data = updated_doc.to_dict()
    data['id'] = updated_doc.id
    
    # Descriptografa o endereço para a resposta da API
    if 'endereco' in data and data['endereco']:
        endereco_descriptografado = {}
        for key, value in data['endereco'].items():
            if value is not None and isinstance(value, str) and value.strip():
                try:
                    endereco_descriptografado[key] = decrypt_data(value)
                except Exception as e:
                    logger.error(f"Erro ao descriptografar campo de endereço {key} do paciente {paciente_id}: {e}")
                    endereco_descriptografado[key] = "[Erro na descriptografia]"
            else:
                endereco_descriptografado[key] = value
        data['endereco'] = endereco_descriptografado
    
    return data


# =================================================================================
# FUNÇÕES DE SUPORTE PSICOLÓGICO
# =================================================================================

def _detectar_tipo_conteudo(conteudo: str) -> str:
    """Detecta se o conteúdo é um link ou texto simples."""
    if conteudo.strip().lower().startswith(('http://', 'https://')):
        return "link"
    return "texto"

def criar_suporte_psicologico(
    db: firestore.client,
    paciente_id: str,
    negocio_id: str,
    suporte_data: schemas.SuportePsicologicoCreate,
    criado_por_id: str
) -> Dict:
    """Cria um novo recurso de suporte psicológico para um paciente, criptografando dados sensíveis."""
    suporte_dict = suporte_data.model_dump()
    
    # Criptografa campos sensíveis antes de salvar
    sensitive_fields = ['titulo', 'conteudo']
    for field in sensitive_fields:
        if field in suporte_dict and suporte_dict[field] is not None:
            if isinstance(suporte_dict[field], str) and suporte_dict[field].strip():
                suporte_dict[field] = encrypt_data(suporte_dict[field])
    
    suporte_dict.update({
        "paciente_id": paciente_id,
        "negocio_id": negocio_id,
        "criado_por": criado_por_id,
        "tipo": _detectar_tipo_conteudo(suporte_data.conteudo),  # Usa o conteúdo original para detectar o tipo
        "data_criacao": firestore.SERVER_TIMESTAMP,
        "data_atualizacao": firestore.SERVER_TIMESTAMP,
    })
    
    doc_ref = db.collection('usuarios').document(paciente_id).collection('suporte_psicologico').document()
    doc_ref.set(suporte_dict)
    
    # Para a resposta, substituímos o ServerTimestamp por um datetime real e descriptografamos
    suporte_dict['id'] = doc_ref.id

    # NOVA LINHA: Notificar paciente sobre o suporte adicionado
    _notificar_paciente_suporte_adicionado(db, paciente_id, suporte_dict)
    now = datetime.utcnow()
    suporte_dict['data_criacao'] = now
    suporte_dict['data_atualizacao'] = now
    
    # Descriptografa campos sensíveis para a resposta da API
    for field in sensitive_fields:
        if field in suporte_dict and suporte_dict[field] is not None:
            if isinstance(suporte_dict[field], str) and suporte_dict[field].strip():
                try:
                    suporte_dict[field] = decrypt_data(suporte_dict[field])
                except Exception as e:
                    logger.error(f"Erro ao descriptografar campo {field} do suporte psicológico: {e}")
                    suporte_dict[field] = "[Erro na descriptografia]"
    
    return suporte_dict

def listar_suportes_psicologicos(db: firestore.client, paciente_id: str) -> List[Dict]:
    """Lista todos os recursos de suporte psicológico de um paciente, descriptografando dados sensíveis."""
    suportes = []
    query = db.collection('usuarios').document(paciente_id).collection('suporte_psicologico').order_by('data_criacao', direction=firestore.Query.DESCENDING)
    
    # Define campos sensíveis que precisam ser descriptografados
    sensitive_fields = ['titulo', 'conteudo']
    
    for doc in query.stream():
        data = doc.to_dict()
        data['id'] = doc.id
        
        # Descriptografa campos sensíveis
        for field in sensitive_fields:
            if field in data and data[field] is not None:
                if isinstance(data[field], str) and data[field].strip():
                    try:
                        data[field] = decrypt_data(data[field])
                    except Exception as e:
                        logger.error(f"Erro ao descriptografar campo {field} do suporte psicológico {doc.id}: {e}")
                        data[field] = "[Erro na descriptografia]"
        
        suportes.append(data)
    return suportes

def atualizar_suporte_psicologico(
    db: firestore.client,
    paciente_id: str,
    suporte_id: str,
    update_data: schemas.SuportePsicologicoUpdate
) -> Optional[Dict]:
    """Atualiza um recurso de suporte psicológico existente, criptografando novos dados sensíveis."""
    suporte_ref = db.collection('usuarios').document(paciente_id).collection('suporte_psicologico').document(suporte_id)
    if not suporte_ref.get().exists:
        return None
        
    update_dict = update_data.model_dump(exclude_unset=True)
    
    # Define campos sensíveis que precisam ser criptografados
    sensitive_fields = ['titulo', 'conteudo']
    
    # Se o conteúdo for atualizado, reavalia o tipo usando o conteúdo original antes da criptografia
    if 'conteudo' in update_dict:
        update_dict['tipo'] = _detectar_tipo_conteudo(update_dict['conteudo'])
    
    # Criptografa campos sensíveis que estão sendo atualizados
    for field in sensitive_fields:
        if field in update_dict and update_dict[field] is not None:
            if isinstance(update_dict[field], str) and update_dict[field].strip():
                update_dict[field] = encrypt_data(update_dict[field])
        
    update_dict['data_atualizacao'] = firestore.SERVER_TIMESTAMP
    suporte_ref.update(update_dict)
    
    updated_doc = suporte_ref.get()
    data = updated_doc.to_dict()
    data['id'] = updated_doc.id
    
    # Descriptografa campos sensíveis para a resposta da API
    for field in sensitive_fields:
        if field in data and data[field] is not None:
            if isinstance(data[field], str) and data[field].strip():
                try:
                    data[field] = decrypt_data(data[field])
                except Exception as e:
                    logger.error(f"Erro ao descriptografar campo {field} do suporte psicológico {suporte_id}: {e}")
                    data[field] = "[Erro na descriptografia]"
    
    return data

def deletar_suporte_psicologico(db: firestore.client, paciente_id: str, suporte_id: str) -> bool:
    """Deleta um recurso de suporte psicológico."""
    suporte_ref = db.collection('usuarios').document(paciente_id).collection('suporte_psicologico').document(suporte_id)
    if not suporte_ref.get().exists:
        return False
    suporte_ref.delete()
    return True

# =================================================================================
# NOVA FUNÇÃO: CONSENTIMENTO LGPD
# =================================================================================

def atualizar_consentimento_lgpd(db: firestore.client, user_id: str, consent_data: schemas.ConsentimentoLGPDUpdate) -> Optional[Dict]:
    """
    Atualiza os dados de consentimento LGPD para um usuário específico.
    """
    user_ref = db.collection('usuarios').document(user_id)
    user_doc = user_ref.get()

    if not user_doc.exists:
        logger.warning(f"Tentativa de atualizar consentimento de usuário inexistente: {user_id}")
        return None

    # Converte o modelo Pydantic para um dicionário para o Firestore
    update_dict = consent_data.model_dump()
    
    # Garante que o enum seja salvo como string
    update_dict['tipo_consentimento'] = update_dict['tipo_consentimento'].value

    user_ref.update(update_dict)
    logger.info(f"Consentimento LGPD atualizado para o usuário {user_id}.")

    # Retorna o documento completo e atualizado
    updated_doc = user_ref.get()
    data = updated_doc.to_dict()
    data['id'] = updated_doc.id
    
    # Descriptografa campos sensíveis do usuário
    if 'nome' in data and data['nome']:
        try:
            data['nome'] = decrypt_data(data['nome'])
        except Exception as e:
            logger.error(f"Erro ao descriptografar nome do usuário {updated_doc.id}: {e}")
            data['nome'] = "[Erro na descriptografia]"
    
    if 'telefone' in data and data['telefone']:
        try:
            data['telefone'] = decrypt_data(data['telefone'])
        except Exception as e:
            logger.error(f"Erro ao descriptografar telefone do usuário {updated_doc.id}: {e}")
            data['telefone'] = "[Erro na descriptografia]"
    
    if 'endereco' in data and data['endereco']:
        endereco_descriptografado = {}
        for key, value in data['endereco'].items():
            if value and isinstance(value, str) and value.strip():
                try:
                    endereco_descriptografado[key] = decrypt_data(value)
                except Exception as e:
                    logger.error(f"Erro ao descriptografar campo de endereço {key} do usuário {updated_doc.id}: {e}")
                    endereco_descriptografado[key] = "[Erro na descriptografia]"
            else:
                endereco_descriptografado[key] = value
        data['endereco'] = endereco_descriptografado
    
    return data


# =================================================================================
# FUNÇÕES DE RELATÓRIO MÉDICO
# =================================================================================

# Em crud.py, substitua esta função

def criar_relatorio_medico(db: firestore.client, paciente_id: str, relatorio_data: schemas.RelatorioMedicoCreate, autor: schemas.UsuarioProfile) -> Dict:
    """
    Cria um novo relatório médico para um paciente.
    """
    # 1. Encontrar a consulta mais recente (plano de cuidado ativo)
    consultas = listar_consultas(db, paciente_id)
    if not consultas:
        raise HTTPException(status_code=404, detail="Nenhum plano de cuidado (consulta) encontrado para este paciente.")
    
    consulta_id_recente = consultas[0]['id']

    # 2. Montar o dicionário do novo relatório
    relatorio_dict = {
        "paciente_id": paciente_id,
        "negocio_id": relatorio_data.negocio_id,
        "criado_por_id": autor.id,
        "medico_id": relatorio_data.medico_id,
        "consulta_id": consulta_id_recente,
        "conteudo": relatorio_data.conteudo,
        "status": "pendente",
        "fotos": [],
        "motivo_recusa": None,
        "data_criacao": datetime.utcnow(),
        "data_revisao": None,
    }

    # 3. Salvar no Firestore
    doc_ref = db.collection('relatorios_medicos').document()
    doc_ref.set(relatorio_dict)
    relatorio_dict['id'] = doc_ref.id
    
    # --- INÍCIO DA ALTERAÇÃO ---
    # 4. Notificar o médico sobre o novo relatório
    try:
        _notificar_medico_novo_relatorio(db, relatorio_dict)
    except Exception as e:
        logger.error(f"Falha ao disparar notificação para novo relatório {doc_ref.id}: {e}")
    # --- FIM DA ALTERAÇÃO ---

    logger.info(f"Relatório médico {doc_ref.id} criado para o paciente {paciente_id} pelo usuário {autor.id}.")
    
    return relatorio_dict

def listar_relatorios_por_paciente(db: firestore.client, paciente_id: str) -> List[Dict]:
    """
    Lista todos os relatórios médicos de um paciente específico, ordenados por data de criação.
    """
    relatorios = []
    try:
        query = db.collection('relatorios_medicos') \
            .where('paciente_id', '==', paciente_id) \
            .order_by('data_criacao', direction=firestore.Query.DESCENDING)
        
        profissionais_cache = {}
        
        for doc in query.stream():
            data = doc.to_dict()
            data['id'] = doc.id
            
            # Adiciona informações do médico se disponível
            medico_id = data.get('medico_id')
            if medico_id:
                if medico_id in profissionais_cache:
                    data['medico_nome'] = profissionais_cache[medico_id]['nome']
                else:
                    medico_doc = db.collection('usuarios').document(medico_id).get()
                    if medico_doc.exists:
                        medico_data = medico_doc.to_dict()
                        nome_medico = medico_data.get('nome', 'Médico desconhecido')
                        # --- INÍCIO DA CORREÇÃO ---
                        if nome_medico and nome_medico != 'Médico desconhecido':
                            try:
                                nome_medico = decrypt_data(nome_medico)
                            except Exception as e:
                                logger.error(f"Erro ao descriptografar nome do médico {medico_id}: {e}")
                                nome_medico = "[Erro na descriptografia]"
                        # --- FIM DA CORREÇÃO ---
                        
                        profissionais_cache[medico_id] = {'nome': nome_medico}
                        data['medico_nome'] = nome_medico
                    else:
                        data['medico_nome'] = 'Médico não encontrado'
            
            # Adiciona informações do criador se disponível
            criado_por_id = data.get('criado_por_id')
            if criado_por_id and criado_por_id != medico_id:
                if criado_por_id in profissionais_cache:
                    data['criado_por_nome'] = profissionais_cache[criado_por_id]['nome']
                else:
                    criador_doc = db.collection('usuarios').document(criado_por_id).get()
                    if criador_doc.exists:
                        criador_data = criador_doc.to_dict()
                        nome_criador = criador_data.get('nome', 'Criador desconhecido')
                        # --- INÍCIO DA CORREÇÃO ---
                        if nome_criador and nome_criador != 'Criador desconhecido':
                            try:
                                nome_criador = decrypt_data(nome_criador)
                            except Exception as e:
                                logger.error(f"Erro ao descriptografar nome do criador {criado_por_id}: {e}")
                                nome_criador = "[Erro na descriptografia]"
                        # --- FIM DA CORREÇÃO ---
                        
                        profissionais_cache[criado_por_id] = {'nome': nome_criador}
                        data['criado_por_nome'] = nome_criador
                    else:
                        data['criado_por_nome'] = 'Criador não encontrado'
            
            relatorios.append(data)
        
        # --- CORREÇÃO ADICIONAL: MOVER O RETURN PARA FORA DO LOOP ---
        return relatorios
            
    except Exception as e:
        logger.error(f"Erro ao listar relatórios para o paciente {paciente_id}: {e}")
        # --- CORREÇÃO ADICIONAL: RETORNAR LISTA VAZIA EM CASO DE ERRO NA QUERY ---
        return []
    
            
def adicionar_foto_relatorio(db: firestore.client, relatorio_id: str, foto_url: str) -> Optional[Dict]:
    """Adiciona a URL de uma foto ao array 'fotos' de um relatório médico usando operação atômica (ArrayUnion)."""
    try:
        relatorio_ref = db.collection('relatorios_medicos').document(relatorio_id)
        snapshot = relatorio_ref.get()
        if not snapshot.exists:
            logger.error(f"Relatório {relatorio_id} não encontrado.")
            return None

        # Operação atômica no servidor: evita sobrescrita do array e é segura em concorrência
        relatorio_ref.update({ "fotos": firestore.ArrayUnion([foto_url]) })

        # Retorna documento atualizado
        updated = relatorio_ref.get()
        data = updated.to_dict() or {}
        data["id"] = updated.id
        return data
    except Exception as e:
        logger.error(f"Erro ao adicionar foto (ArrayUnion) ao relatório {relatorio_id}: {e}")
        raise

def listar_relatorios_pendentes_medico(db: firestore.client, medico_id: str, negocio_id: str) -> List[Dict]:
    """
    Lista todos os relatórios com status 'pendente' atribuídos a um médico específico.
    """
    relatorios = []
    try:
        # Log dos parâmetros de entrada
        logger.info(f"🔍 DEBUG RELATÓRIOS PENDENTES:")
        logger.info(f"   - medico_id: {medico_id}")
        logger.info(f"   - negocio_id: {negocio_id}")
        logger.info(f"   - status: pendente")
        
        # Primeiro, vamos verificar se existem relatórios com esse médico em geral
        query_medico = db.collection('relatorios_medicos').where('medico_id', '==', medico_id)
        count_medico = len(list(query_medico.stream()))
        logger.info(f"   - Total de relatórios para este médico: {count_medico}")
        
        # Verificar se existem relatórios com esse negócio
        query_negocio = db.collection('relatorios_medicos').where('negocio_id', '==', negocio_id)
        count_negocio = len(list(query_negocio.stream()))
        logger.info(f"   - Total de relatórios para este negócio: {count_negocio}")
        
        # Verificar se existem relatórios pendentes em geral
        query_pendentes = db.collection('relatorios_medicos').where('status', '==', 'pendente')
        count_pendentes = len(list(query_pendentes.stream()))
        logger.info(f"   - Total de relatórios pendentes no sistema: {count_pendentes}")
        
        # Query sem ordenação para evitar erro de índice
        # TODO: Criar índice composto no Firestore para incluir order_by
        query = db.collection('relatorios_medicos') \
            .where('negocio_id', '==', negocio_id) \
            .where('medico_id', '==', medico_id) \
            .where('status', '==', 'pendente')
        
        for doc in query.stream():
            data = doc.to_dict()
            data['id'] = doc.id
            
            # Buscar e incluir dados do paciente
            paciente_id = data.get('paciente_id')
            if paciente_id:
                try:
                    paciente_doc = db.collection('usuarios').document(paciente_id).get()
                    if paciente_doc.exists:
                        paciente_data = paciente_doc.to_dict()
                        
                        # Descriptografar dados sensíveis do paciente
                        paciente_info = {
                            'id': paciente_id,
                            'email': paciente_data.get('email', '')
                        }
                        
                        # Descriptografar nome
                        if 'nome' in paciente_data and paciente_data['nome']:
                            try:
                                paciente_info['nome'] = decrypt_data(paciente_data['nome'])
                            except Exception as e:
                                logger.error(f"Erro ao descriptografar nome do paciente {paciente_id}: {e}")
                                paciente_info['nome'] = "[Erro na descriptografia]"
                        else:
                            paciente_info['nome'] = "Nome não disponível"
                        
                        # Descriptografar telefone se disponível
                        if 'telefone' in paciente_data and paciente_data['telefone']:
                            try:
                                paciente_info['telefone'] = decrypt_data(paciente_data['telefone'])
                            except Exception as e:
                                logger.error(f"Erro ao descriptografar telefone do paciente {paciente_id}: {e}")
                                paciente_info['telefone'] = "[Erro na descriptografia]"
                        
                        # Adicionar dados pessoais básicos se disponíveis
                        if 'data_nascimento' in paciente_data:
                            paciente_info['data_nascimento'] = paciente_data['data_nascimento']
                        if 'sexo' in paciente_data:
                            paciente_info['sexo'] = paciente_data['sexo']
                        if 'estado_civil' in paciente_data:
                            paciente_info['estado_civil'] = paciente_data['estado_civil']
                        if 'profissao' in paciente_data:
                            paciente_info['profissao'] = paciente_data['profissao']
                        
                        data['paciente'] = paciente_info
                    else:
                        data['paciente'] = {
                            'id': paciente_id,
                            'nome': 'Paciente não encontrado',
                            'email': ''
                        }
                        logger.warning(f"Paciente {paciente_id} não encontrado para relatório {doc.id}")
                except Exception as e:
                    logger.error(f"Erro ao buscar dados do paciente {paciente_id}: {e}")
                    data['paciente'] = {
                        'id': paciente_id,
                        'nome': 'Erro ao carregar dados',
                        'email': ''
                    }
            
            relatorios.append(data)
            logger.info(f"✅ Relatório encontrado: {doc.id}")
            logger.info(f"   - medico_id: {data.get('medico_id')}")
            logger.info(f"   - negocio_id: {data.get('negocio_id')}")
            logger.info(f"   - status: {data.get('status')}")
            logger.info(f"   - paciente: {data.get('paciente', {}).get('nome', 'N/A')}")
        
        # Ordenar manualmente por data_criacao (mais recente primeiro)
        relatorios.sort(key=lambda x: x.get('data_criacao', datetime.min), reverse=True)
        
        logger.info(f"📊 RESULTADO FINAL: {len(relatorios)} relatórios pendentes encontrados")
        
        # Se não encontrou nada, vamos verificar os relatórios específicos mencionados no bug report
        if len(relatorios) == 0:
            logger.warning("❌ Nenhum relatório encontrado! Verificando relatórios específicos...")
            relatorio_ids_debug = ["6O75Oh2o9rHggN8oXUhj", "Qb0y0CeCADAlzdUxTtGN"]
            
            for relatorio_id in relatorio_ids_debug:
                doc_ref = db.collection('relatorios_medicos').document(relatorio_id)
                doc = doc_ref.get()
                if doc.exists:
                    data = doc.to_dict()
                    logger.info(f"🔍 Relatório específico {relatorio_id}:")
                    logger.info(f"   - medico_id: {data.get('medico_id')} (esperado: {medico_id})")
                    logger.info(f"   - negocio_id: {data.get('negocio_id')} (esperado: {negocio_id})")
                    logger.info(f"   - status: {data.get('status')} (esperado: pendente)")
                    logger.info(f"   - data_criacao: {data.get('data_criacao')}")
                    
                    # Verificar se os valores são exatamente iguais
                    medico_match = data.get('medico_id') == medico_id
                    negocio_match = data.get('negocio_id') == negocio_id
                    status_match = data.get('status') == 'pendente'
                    
                    logger.info(f"   - medico_id match: {medico_match}")
                    logger.info(f"   - negocio_id match: {negocio_match}")
                    logger.info(f"   - status match: {status_match}")
                else:
                    logger.warning(f"❌ Relatório {relatorio_id} não existe no banco!")
            
    except Exception as e:
        logger.error(f"Erro ao listar relatórios pendentes para o médico {medico_id}: {e}")
        # Log do stack trace completo para debug
        import traceback
        logger.error(f"Stack trace: {traceback.format_exc()}")
    return relatorios

# SUBSTITUA A FUNÇÃO 'aprovar_relatorio' INTEIRA PELA VERSÃO ABAIXO

# SUBSTITUA ESTA FUNÇÃO INTEIRA NO SEU ARQUIVO crud.py

def aprovar_relatorio(db: firestore.client, relatorio_id: str, medico_id: str) -> Optional[Dict]:
    """
    Muda o status de um relatório para 'aprovado' e notifica o criador, usando o método de envio individual.
    """
    print(f"--- INICIANDO APROVAÇÃO DO RELATÓRIO {relatorio_id} PELO MÉDICO {medico_id} ---")
    relatorio_ref = db.collection('relatorios_medicos').document(relatorio_id)
    relatorio_doc = relatorio_ref.get()

    if not relatorio_doc.exists or relatorio_doc.to_dict().get('medico_id') != medico_id:
        print(f"[ERRO] Acesso negado ou relatório não encontrado.")
        raise HTTPException(status_code=403, detail="Acesso negado: este relatório não está atribuído a você.")

    # 1. Atualiza o status do relatório no banco
    print("[PASSO 1] Atualizando status do relatório para 'aprovado'.")
    relatorio_ref.update({
        "status": "aprovado",
        "data_revisao": datetime.utcnow()
    })
    
    updated_doc = relatorio_ref.get()
    relatorio = updated_doc.to_dict()
    relatorio['id'] = updated_doc.id
    print("[PASSO 1] Status atualizado com sucesso.")
    
    # --- INÍCIO DA LÓGICA DE NOTIFICAÇÃO DIRETA ---
    print("\n--- INICIANDO LÓGICA DE NOTIFICAÇÃO ---")
    try:
        criado_por_id = relatorio.get('criado_por_id')
        paciente_id = relatorio.get('paciente_id')
        status = "aprovado"

        if not criado_por_id:
            print("[ERRO DE NOTIFICAÇÃO] 'criado_por_id' não encontrado no relatório. Abortando notificação.")
            return relatorio

        print(f"[PASSO 2] IDs coletados: criador={criado_por_id}, paciente={paciente_id}")

        # Busca os nomes para montar a mensagem
        medico_doc = db.collection('usuarios').document(medico_id).get()
        nome_medico = decrypt_data(medico_doc.to_dict().get('nome', '')) if medico_doc.exists else "Médico"
        
        paciente_doc = db.collection('usuarios').document(paciente_id).get()
        nome_paciente = decrypt_data(paciente_doc.to_dict().get('nome', '')) if paciente_doc.exists else "Paciente"
        print(f"[PASSO 3] Nomes obtidos: medico='{nome_medico}', paciente='{nome_paciente}'")

        # Busca os dados do criador para pegar os tokens FCM
        criador_doc = db.collection('usuarios').document(criado_por_id).get()
        if not criador_doc.exists:
            print(f"[ERRO DE NOTIFICAÇÃO] Documento do criador '{criado_por_id}' não encontrado.")
            return relatorio
        
        criador_data = criador_doc.to_dict()
        tokens_fcm = criador_data.get('fcm_tokens', [])
        print(f"[PASSO 4] Destinatário encontrado: '{criador_data.get('email')}'. Tokens FCM: {len(tokens_fcm)}")

        # Define o título e o corpo da notificação VISÍVEL
        titulo = "Relatório Avaliado"
        corpo = f"O Dr(a). {nome_medico} aprovou o relatório do paciente {nome_paciente}."

        # Define o payload de DADOS para o app
        data_payload = {
            "tipo": "RELATORIO_AVALIADO",
            "relatorio_id": relatorio.get('id', ''),
            "paciente_id": str(paciente_id),
            "status": status,
        }
        print(f"[PASSO 5] Payloads montados. Título: '{titulo}', Corpo: '{corpo}'")

        # Salva a notificação no histórico do usuário no Firestore
        db.collection('usuarios').document(criado_por_id).collection('notificacoes').add({
            "title": titulo, "body": corpo, "tipo": "RELATORIO_AVALIADO",
            "relacionado": { "relatorio_id": relatorio.get('id'), "paciente_id": paciente_id },
            "lida": False, "data_criacao": firestore.SERVER_TIMESTAMP
        })
        print(f"[PASSO 6] Notificação persistida no Firestore para o usuário {criado_por_id}.")

        # Envia a notificação push se houver tokens
        if tokens_fcm:
            print(f"[PASSO 7] Enviando notificação para {len(tokens_fcm)} token(s) em loop...")
            
            # ** AQUI ESTÁ A CORREÇÃO CRÍTICA **
            # Usando loop com messaging.send() em vez de send_multicast()
            sucessos = 0
            falhas = 0
            for token in tokens_fcm:
                try:
                    message = messaging.Message(
                        notification=messaging.Notification(title=titulo, body=corpo),
                        data=data_payload,
                        token=token
                    )
                    messaging.send(message)
                    sucessos += 1
                except Exception as e:
                    falhas += 1
                    logger.error(f"Erro ao enviar para o token {token[:10]}...: {e}")

            print(f"[PASSO 7 SUCESSO] Envio concluído. Sucessos: {sucessos}, Falhas: {falhas}")
        else:
            print("[PASSO 7 FALHA] Nenhum token FCM encontrado para o destinatário. Push não enviado.")
    
    except Exception as e:
        print(f"[ERRO CRÍTICO NA NOTIFICAÇÃO] Exceção: {e}")
        import traceback
        print(traceback.format_exc())
    
    print("--- FINALIZANDO APROVAÇÃO DO RELATÓRIO ---")
    return relatorio

def recusar_relatorio(db: firestore.client, relatorio_id: str, medico_id: str, motivo: str) -> Optional[Dict]:
    """
    Muda o status de um relatório para 'recusado' e adiciona o motivo.
    """
    relatorio_ref = db.collection('relatorios_medicos').document(relatorio_id)
    relatorio_doc = relatorio_ref.get()

    if not relatorio_doc.exists or relatorio_doc.to_dict().get('medico_id') != medico_id:
        raise HTTPException(status_code=403, detail="Acesso negado: este relatório não está atribuído a você.")

    relatorio_ref.update({
        "status": "recusado",
        "data_revisao": datetime.utcnow(),
        "motivo_recusa": motivo
    })
    
    updated_doc = relatorio_ref.get()
    data = updated_doc.to_dict()
    data['id'] = updated_doc.id
    
    # Notificar criador do relatório sobre recusa
    try:
        _notificar_criador_relatorio_avaliado(db, data, "recusado")
    except Exception as e:
        logger.error(f"Erro ao notificar recusa de relatório {relatorio_id}: {e}")
    
    return data

def _notificar_criador_relatorio_avaliado(db: firestore.client, relatorio: Dict, status: str):
    """Notifica o criador do relatório sobre aprovação/recusa pelo médico."""
    try:
        criado_por_id = relatorio.get('criado_por_id')
        medico_id = relatorio.get('medico_id') 
        paciente_id = relatorio.get('paciente_id')
        
        if not criado_por_id:
            logger.warning("Relatório sem criado_por_id. Não é possível notificar.")
            return
            
        medico_doc = db.collection('usuarios').document(medico_id).get()
        if not medico_doc.exists:
            logger.error(f"Médico {medico_id} não encontrado.")
            return
        medico_data = medico_doc.to_dict()
        nome_medico = decrypt_data(medico_data.get('nome', 'Médico')) if medico_data.get('nome') else 'Médico'
        
        paciente_doc = db.collection('usuarios').document(paciente_id).get()
        if not paciente_doc.exists:
            logger.error(f"Paciente {paciente_id} não encontrado.")
            return
        paciente_data = paciente_doc.to_dict()
        nome_paciente = decrypt_data(paciente_data.get('nome', 'Paciente')) if paciente_data.get('nome') else 'Paciente'
        
        criador_doc = db.collection('usuarios').document(criado_por_id).get()
        if not criador_doc.exists:
            logger.error(f"Criador do relatório {criado_por_id} não encontrado.")
            return
        criador_data = criador_doc.to_dict()
        tokens_fcm = criador_data.get('fcm_tokens', [])
        
        titulo = "Relatório Avaliado"
        if status == "aprovado":
            corpo = f"O Dr(a). {nome_medico} aprovou o relatório do paciente {nome_paciente}."
        else:
            corpo = f"O Dr(a). {nome_medico} recusou o relatório do paciente {nome_paciente}."
        
        # CORREÇÃO: 'title' e 'body' removidos daqui
        data_payload = {
            "tipo": "RELATORIO_AVALIADO",
            "relatorio_id": relatorio.get('id'),
            "paciente_id": paciente_id,
            "status": status,
        }
        
        notificacao_data = {
            "title": titulo,
            "body": corpo,
            "tipo": "RELATORIO_AVALIADO",
            "relatorio_id": relatorio.get('id'),
            "paciente_id": paciente_id,
            "status": status,
            "lida": False,
            "data_criacao": datetime.utcnow()
        }
        
        db.collection('usuarios').document(criado_por_id).collection('notificacoes').add(notificacao_data)
        
        if tokens_fcm:
            _send_data_push_to_tokens(db, criador_data.get('firebase_uid'), tokens_fcm, data_payload, titulo, corpo, "RELATORIO_AVALIADO")
            logger.info(f"Notificação de avaliação de relatório enviada para {criado_por_id}")
        else:
            logger.info(f"Usuário {criado_por_id} não possui tokens FCM registrados")
            
    except Exception as e:
        logger.error(f"Erro ao notificar avaliação de relatório: {e}")

def _notificar_tecnicos_plano_atualizado(db: firestore.client, paciente_id: str, consulta_id: str):
    """Notifica todos os técnicos vinculados sobre novo plano de cuidado."""
    try:
        paciente_doc = db.collection('usuarios').document(paciente_id).get()
        if not paciente_doc.exists:
            logger.error(f"Paciente {paciente_id} não encontrado.")
            return
            
        paciente_data = paciente_doc.to_dict()
        nome_paciente = decrypt_data(paciente_data.get('nome', 'Paciente')) if paciente_data.get('nome') else 'Paciente'
        tecnicos_ids = paciente_data.get('tecnicos_ids', [])
        
        if not tecnicos_ids:
            logger.info(f"Paciente {paciente_id} não possui técnicos vinculados.")
            return
            
        titulo = "Plano de Cuidado Atualizado"
        corpo = f"O plano de cuidado do paciente {nome_paciente} foi atualizado. Confirme a leitura para iniciar suas atividades."
        
        # CORREÇÃO: 'title' e 'body' removidos daqui
        data_payload = {
            "tipo": "PLANO_CUIDADO_ATUALIZADO",
            "paciente_id": paciente_id,
            "consulta_id": consulta_id,
        }
        
        for tecnico_id in tecnicos_ids:
            try:
                tecnico_doc = db.collection('usuarios').document(tecnico_id).get()
                if not tecnico_doc.exists:
                    logger.warning(f"Técnico {tecnico_id} não encontrado.")
                    continue
                    
                tecnico_data = tecnico_doc.to_dict()
                tokens_fcm = tecnico_data.get('fcm_tokens', [])
                
                notificacao_data = {
                    "title": titulo,
                    "body": corpo,
                    "tipo": "PLANO_CUIDADO_ATUALIZADO",
                    "paciente_id": paciente_id,
                    "consulta_id": consulta_id,
                    "lida": False,
                    "data_criacao": datetime.utcnow()
                }
                
                db.collection('usuarios').document(tecnico_id).collection('notificacoes').add(notificacao_data)
                
                if tokens_fcm:
                    _send_data_push_to_tokens(db, tecnico_data.get('firebase_uid'), tokens_fcm, data_payload, titulo, corpo, "PLANO_CUIDADO")
                    logger.info(f"Notificação de plano atualizado enviada para técnico {tecnico_id}")
                else:
                    logger.info(f"Técnico {tecnico_id} não possui tokens FCM registrados")
                    
            except Exception as e:
                logger.error(f"Erro ao notificar técnico {tecnico_id}: {e}")
                
        logger.info(f"Notificações de plano atualizado enviadas para {len(tecnicos_ids)} técnicos do paciente {paciente_id}")
        
    except Exception as e:
        logger.error(f"Erro ao notificar técnicos sobre plano atualizado: {e}")


def _notificar_profissional_associacao(db: firestore.client, profissional_id: str, paciente_id: str, tipo_profissional: str):
    """Notifica um profissional (enfermeiro ou técnico) sobre associação a um paciente."""
    try:
        paciente_doc = db.collection('usuarios').document(paciente_id).get()
        if not paciente_doc.exists:
            logger.error(f"Paciente {paciente_id} não encontrado.")
            return
            
        paciente_data = paciente_doc.to_dict()
        nome_paciente = decrypt_data(paciente_data.get('nome', 'Paciente')) if paciente_data.get('nome') else 'Paciente'
        
        profissional_doc = db.collection('usuarios').document(profissional_id).get()
        if not profissional_doc.exists:
            logger.error(f"Profissional {profissional_id} não encontrado.")
            return
        profissional_data = profissional_doc.to_dict()
        tokens_fcm = profissional_data.get('fcm_tokens', [])
        
        titulo = "Você foi associado a um paciente"
        if tipo_profissional == "enfermeiro":
            corpo = f"Você foi associado como enfermeiro responsável pelo paciente {nome_paciente}."
        else:
            corpo = f"Você foi associado à equipe de cuidados do paciente {nome_paciente}."
        
        # CORREÇÃO: 'title' e 'body' removidos daqui
        data_payload = {
            "tipo": "ASSOCIACAO_PACIENTE",
            "paciente_id": paciente_id,
            "tipo_profissional": tipo_profissional,
        }
        
        notificacao_data = {
            "title": titulo,
            "body": corpo,
            "tipo": "ASSOCIACAO_PACIENTE",
            "paciente_id": paciente_id,
            "tipo_profissional": tipo_profissional,
            "lida": False,
            "data_criacao": datetime.utcnow()
        }
        
        db.collection('usuarios').document(profissional_id).collection('notificacoes').add(notificacao_data)
        
        if tokens_fcm:
            _send_data_push_to_tokens(db, profissional_data.get('firebase_uid'), tokens_fcm, data_payload, titulo, corpo, "ASSOCIACAO_PACIENTE")
            logger.info(f"Notificação de associação enviada para {tipo_profissional} {profissional_id}")
        else:
            logger.info(f"{tipo_profissional.capitalize()} {profissional_id} não possui tokens FCM registrados")
            
    except Exception as e:
        logger.error(f"Erro ao notificar profissional sobre associação: {e}")


def _verificar_checklist_completo(db: firestore.client, paciente_id: str, item_id: str):
    """Verifica se o checklist diário está 100% concluído e notifica se necessário."""
    try:
        # Obter o item atualizado para pegar a data
        item_ref = db.collection('usuarios').document(paciente_id).collection('checklist').document(item_id)
        item_doc = item_ref.get()
        if not item_doc.exists:
            return
            
        item_data = item_doc.to_dict()
        data_criacao = item_data.get('data_criacao')
        negocio_id = item_data.get('negocio_id')
        
        if not data_criacao or not negocio_id:
            logger.warning("Item do checklist sem data_criacao ou negocio_id")
            return
            
        # Converter timestamp para data para comparação
        from datetime import datetime
        if hasattr(data_criacao, 'date'):
            data_item = data_criacao.date()
        else:
            # Se for string ou outro formato, tentar converter
            data_item = datetime.fromisoformat(str(data_criacao).split('T')[0]).date()
            
        # Buscar todos os itens do mesmo dia e negócio
        checklist_ref = db.collection('usuarios').document(paciente_id).collection('checklist')
        query = checklist_ref.where('negocio_id', '==', negocio_id)
        
        # Filtrar itens do mesmo dia
        todos_itens = []
        itens_concluidos = 0
        
        for doc in query.stream():
            data_doc = doc.to_dict()
            doc_data_criacao = data_doc.get('data_criacao')
            
            if doc_data_criacao:
                if hasattr(doc_data_criacao, 'date'):
                    doc_data = doc_data_criacao.date()
                else:
                    doc_data = datetime.fromisoformat(str(doc_data_criacao).split('T')[0]).date()
                
                # Se é do mesmo dia
                if doc_data == data_item:
                    todos_itens.append(data_doc)
                    if data_doc.get('concluido', False):
                        itens_concluidos += 1
        
        # Verificar se todos os itens estão concluídos
        total_itens = len(todos_itens)
        if total_itens > 0 and itens_concluidos == total_itens:
            logger.info(f"Checklist 100% concluído para paciente {paciente_id} em {data_item}")
            
            # Obter ID do técnico que fez a última marcação
            # (assumindo que o current_user seria passado, mas vamos buscar pelo ultimo item atualizado)
            # Para simplificar, vamos buscar o enfermeiro e supervisor do paciente
            _notificar_checklist_concluido(db, paciente_id, data_item, negocio_id)
        else:
            logger.info(f"Checklist parcial: {itens_concluidos}/{total_itens} itens concluídos para paciente {paciente_id}")
            
    except Exception as e:
        logger.error(f"Erro ao verificar checklist completo: {e}")

def _notificar_checklist_concluido(db: firestore.client, paciente_id: str, data_checklist: date, negocio_id: str):
    """Notifica enfermeiro e supervisor sobre checklist 100% concluído."""
    try:
        paciente_doc = db.collection('usuarios').document(paciente_id).get()
        if not paciente_doc.exists:
            logger.error(f"Paciente {paciente_id} não encontrado.")
            return
            
        paciente_data = paciente_doc.to_dict()
        nome_paciente = decrypt_data(paciente_data.get('nome', 'Paciente')) if paciente_data.get('nome') else 'Paciente'
        enfermeiro_id = paciente_data.get('enfermeiro_id')
        
        tecnicos_ids = paciente_data.get('tecnicos_ids', [])
        nome_tecnico = "Técnico"
        supervisor_id = None
        
        if tecnicos_ids:
            for tecnico_id in tecnicos_ids:
                tecnico_doc = db.collection('usuarios').document(tecnico_id).get()
                if tecnico_doc.exists:
                    tecnico_data = tecnico_doc.to_dict()
                    nome_tecnico = decrypt_data(tecnico_data.get('nome', 'Técnico')) if tecnico_data.get('nome') else 'Técnico'
                    supervisor_id = tecnico_data.get('supervisor_id')
                    break
        
        titulo = "Checklist Diário Concluído"
        corpo = f"O técnico {nome_tecnico} concluiu o checklist diário do paciente {nome_paciente}."
        
        # CORREÇÃO: 'title' e 'body' removidos daqui
        data_payload = {
            "tipo": "CHECKLIST_CONCLUIDO",
            "paciente_id": paciente_id,
            "data": data_checklist.isoformat(),
        }
        
        destinatarios = set()
        if enfermeiro_id:
            destinatarios.add(enfermeiro_id)
        if supervisor_id:
            destinatarios.add(supervisor_id)
        
        for destinatario_id in destinatarios:
            try:
                destinatario_doc = db.collection('usuarios').document(destinatario_id).get()
                if not destinatario_doc.exists:
                    logger.warning(f"Destinatário {destinatario_id} não encontrado.")
                    continue
                    
                destinatario_data = destinatario_doc.to_dict()
                tokens_fcm = destinatario_data.get('fcm_tokens', [])
                
                notificacao_data = {
                    "title": titulo,
                    "body": corpo,
                    "tipo": "CHECKLIST_CONCLUIDO",
                    "paciente_id": paciente_id,
                    "data": data_checklist.isoformat(),
                    "lida": False,
                    "data_criacao": datetime.utcnow()
                }
                
                db.collection('usuarios').document(destinatario_id).collection('notificacoes').add(notificacao_data)
                
                if tokens_fcm:
                    _send_data_push_to_tokens(db, destinatario_data.get('firebase_uid'), tokens_fcm, data_payload, titulo, corpo, "CHECKLIST_CONCLUIDO")
                    logger.info(f"Notificação de checklist concluído enviada para {destinatario_id}")
                else:
                    logger.info(f"Destinatário {destinatario_id} não possui tokens FCM registrados")
                    
            except Exception as e:
                logger.error(f"Erro ao notificar destinatário {destinatario_id}: {e}")
                
        logger.info(f"Notificações de checklist concluído enviadas para {len(destinatarios)} pessoas")
        
    except Exception as e:
        logger.error(f"Erro ao notificar checklist concluído: {e}")


def atualizar_dados_pessoais_paciente(db: firestore.client, paciente_id: str, dados_pessoais: schemas.PacienteUpdateDadosPessoais) -> Optional[Dict]:
    """
    Atualiza os dados pessoais básicos de um paciente.
    Estes campos foram migrados da anamnese para centralizar no nível do paciente.
    """
    try:
        user_ref = db.collection("usuarios").document(paciente_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            logger.error(f"Paciente {paciente_id} não encontrado.")
            return None
        
        # Preparar dados para atualização (apenas campos não-None)
        update_data = {}
        
        if dados_pessoais.data_nascimento is not None:
            update_data["data_nascimento"] = dados_pessoais.data_nascimento
        if dados_pessoais.sexo is not None:
            update_data["sexo"] = dados_pessoais.sexo  
        if dados_pessoais.estado_civil is not None:
            update_data["estado_civil"] = dados_pessoais.estado_civil
        if dados_pessoais.profissao is not None:
            update_data["profissao"] = dados_pessoais.profissao
        if dados_pessoais.nome is not None:
            update_data["nome"] = encrypt_data(dados_pessoais.nome)
        if dados_pessoais.telefone is not None:
            update_data["telefone"] = encrypt_data(dados_pessoais.telefone) if dados_pessoais.telefone else None
        
        # Atualizar endereço se fornecido
        if dados_pessoais.endereco is not None:
            endereco_criptografado = {
                "rua": encrypt_data(dados_pessoais.endereco.rua),
                "numero": encrypt_data(dados_pessoais.endereco.numero),
                "cidade": encrypt_data(dados_pessoais.endereco.cidade),
                "estado": encrypt_data(dados_pessoais.endereco.estado),
                "cep": encrypt_data(dados_pessoais.endereco.cep)
            }
            update_data["endereco"] = endereco_criptografado
        
        if not update_data:
            logger.info(f"Nenhum campo para atualizar no paciente {paciente_id}")
            # Retornar dados atuais descriptografados
            current_data = user_doc.to_dict()
            current_data["id"] = user_doc.id
            # Descriptografar dados sensíveis manualmente
            if "nome" in current_data and current_data["nome"]:
                try:
                    current_data["nome"] = decrypt_data(current_data["nome"])
                except Exception as e:
                    logger.error(f"Erro ao descriptografar nome: {e}")
                    current_data["nome"] = "[Erro na descriptografia]"
            if "telefone" in current_data and current_data["telefone"]:
                try:
                    current_data["telefone"] = decrypt_data(current_data["telefone"])
                except Exception as e:
                    logger.error(f"Erro ao descriptografar telefone: {e}")
                    current_data["telefone"] = "[Erro na descriptografia]"
            if "endereco" in current_data and current_data["endereco"]:
                endereco_descriptografado = {}
                for key, value in current_data["endereco"].items():
                    if value and isinstance(value, str) and value.strip():
                        try:
                            endereco_descriptografado[key] = decrypt_data(value)
                        except Exception as e:
                            logger.error(f"Erro ao descriptografar campo {key} do endereço: {e}")
                            endereco_descriptografado[key] = "[Erro na descriptografia]"
                    else:
                        endereco_descriptografado[key] = value
                current_data["endereco"] = endereco_descriptografado
            return current_data
        
        # Atualizar documento
        user_ref.update(update_data)
        logger.info(f"Paciente {paciente_id} atualizado com sucesso: {list(update_data.keys())}")
        
        # Retornar documento atualizado
        updated_doc = user_ref.get()
        updated_data = updated_doc.to_dict()
        updated_data["id"] = updated_doc.id
        
        # Descriptografar dados sensíveis para resposta
        if "nome" in updated_data and updated_data["nome"]:
            try:
                updated_data["nome"] = decrypt_data(updated_data["nome"])
            except Exception as e:
                logger.error(f"Erro ao descriptografar nome: {e}")
                updated_data["nome"] = "[Erro na descriptografia]"
        if "telefone" in updated_data and updated_data["telefone"]:
            try:
                updated_data["telefone"] = decrypt_data(updated_data["telefone"])
            except Exception as e:
                logger.error(f"Erro ao descriptografar telefone: {e}")
                updated_data["telefone"] = "[Erro na descriptografia]"
        if "endereco" in updated_data and updated_data["endereco"]:
            endereco_descriptografado = {}
            for key, value in updated_data["endereco"].items():
                if value and isinstance(value, str) and value.strip():
                    try:
                        endereco_descriptografado[key] = decrypt_data(value)
                    except Exception as e:
                        logger.error(f"Erro ao descriptografar campo {key} do endereço: {e}")
                        endereco_descriptografado[key] = "[Erro na descriptografia]"
                else:
                    endereco_descriptografado[key] = value
            updated_data["endereco"] = endereco_descriptografado
        
        return updated_data
        
    except Exception as e:
        logger.error(f"Erro ao atualizar dados pessoais do paciente {paciente_id}: {e}")
        return None


def atualizar_relatorio_medico(db: firestore.client, relatorio_id: str, update_data: schemas.RelatorioMedicoUpdate, usuario_id: str) -> Optional[Dict]:
    """
    Atualiza um relatório médico com novos dados.
    """
    try:
        relatorio_ref = db.collection("relatorios_medicos").document(relatorio_id)
        relatorio_doc = relatorio_ref.get()
        
        if not relatorio_doc.exists:
            logger.error(f"Relatório {relatorio_id} não encontrado.")
            return None
        
        # Verificar se o usuário tem permissão para editar
        relatorio_data = relatorio_doc.to_dict()
        if relatorio_data.get("criado_por_id") != usuario_id:
            logger.warning(f"Usuário {usuario_id} tentou editar relatório {relatorio_id} de outro usuário.")
            raise HTTPException(status_code=403, detail="Acesso negado: você só pode editar seus próprios relatórios.")
        
        # Preparar dados para atualização
        update_dict = {}
        
        if update_data.conteudo is not None:
            update_dict["conteudo"] = update_data.conteudo
        if update_data.status is not None:
            update_dict["status"] = update_data.status
        if update_data.motivo_recusa is not None:
            update_dict["motivo_recusa"] = update_data.motivo_recusa
        
        if not update_dict:
            logger.info(f"Nenhum campo para atualizar no relatório {relatorio_id}")
            current_data = relatorio_doc.to_dict()
            current_data["id"] = relatorio_doc.id
            return current_data
        
        # Atualizar documento
        relatorio_ref.update(update_dict)
        logger.info(f"Relatório {relatorio_id} atualizado com sucesso: {list(update_dict.keys())}")
        
        # Retornar documento atualizado
        updated_doc = relatorio_ref.get()
        updated_data = updated_doc.to_dict()
        updated_data["id"] = updated_doc.id
        
        return updated_data
        
    except Exception as e:
        logger.error(f"Erro ao atualizar relatório {relatorio_id}: {e}")
        return None


def listar_historico_relatorios_medico(db: firestore.client, medico_id: str, negocio_id: str, status_filter: Optional[str] = None) -> List[Dict]:
    """
    Lista o histórico de relatórios já avaliados pelo médico (aprovados + recusados).
    
    Args:
        db: Cliente Firestore
        medico_id: ID do médico
        negocio_id: ID do negócio
        status_filter: Filtro opcional por status ('aprovado' ou 'recusado')
    
    Returns:
        Lista de relatórios com dados do paciente descriptografados
    """
    try:
        logger.info(f"🔍 DEBUG HISTÓRICO RELATÓRIOS:")
        logger.info(f"   - medico_id: {medico_id}")
        logger.info(f"   - negocio_id: {negocio_id}")
        logger.info(f"   - status_filter: {status_filter}")
        
        # Verificar se existem relatórios para este médico em geral
        query_medico = db.collection('relatorios_medicos').where('medico_id', '==', medico_id)
        count_medico = len(list(query_medico.stream()))
        logger.info(f"   - Total de relatórios para este médico: {count_medico}")
        
        # Verificar relatórios aprovados/recusados para este médico
        query_aprovados_geral = db.collection('relatorios_medicos').where('medico_id', '==', medico_id).where('status', '==', 'aprovado')
        count_aprovados = len(list(query_aprovados_geral.stream()))
        query_recusados_geral = db.collection('relatorios_medicos').where('medico_id', '==', medico_id).where('status', '==', 'recusado')
        count_recusados = len(list(query_recusados_geral.stream()))
        logger.info(f"   - Relatórios aprovados para este médico: {count_aprovados}")
        logger.info(f"   - Relatórios recusados para este médico: {count_recusados}")
        
        # Query base - relatórios avaliados pelo médico no negócio
        query = db.collection("relatorios_medicos") \
            .where("medico_id", "==", medico_id) \
            .where("negocio_id", "==", negocio_id)
        
        # Se status específico foi fornecido, filtrar por ele
        if status_filter and status_filter.lower() in ['aprovado', 'recusado']:
            query = query.where("status", "==", status_filter.lower())
        else:
            # Sem filtro específico - buscar apenas aprovados e recusados
            # Como Firestore não suporta "IN" com outros filtros, fazemos duas queries
            query_aprovados = query.where("status", "==", "aprovado")
            query_recusados = query.where("status", "==", "recusado")
            
            # Executar ambas as queries e combinar resultados
            docs_aprovados = list(query_aprovados.stream())
            docs_recusados = list(query_recusados.stream())
            docs = docs_aprovados + docs_recusados
        
        if status_filter:
            docs = list(query.stream())
        
        logger.info(f"Encontrados {len(docs)} relatórios avaliados")
        
        if not docs:
            return []
        
        relatorios = []
        
        for doc in docs:
            relatorio_data = doc.to_dict()
            relatorio_data["id"] = doc.id
            
            # Buscar dados do paciente
            paciente_id = relatorio_data.get("paciente_id")
            if paciente_id:
                try:
                    paciente_ref = db.collection("usuarios").document(paciente_id)
                    paciente_doc = paciente_ref.get()
                    
                    if paciente_doc.exists:
                        paciente_data = paciente_doc.to_dict()
                        
                        # Descriptografar dados sensíveis do paciente para médicos
                        if 'nome' in paciente_data and paciente_data['nome']:
                            try:
                                paciente_data['nome'] = decrypt_data(paciente_data['nome'])
                            except Exception as e:
                                logger.error(f"Erro ao descriptografar nome do paciente {paciente_id}: {e}")
                                paciente_data['nome'] = "[Erro na descriptografia]"
                        
                        if 'email' in paciente_data and paciente_data['email']:
                            try:
                                paciente_data['email'] = decrypt_data(paciente_data['email'])
                            except Exception as e:
                                logger.error(f"Erro ao descriptografar email do paciente {paciente_id}: {e}")
                                paciente_data['email'] = "[Erro na descriptografia]"
                        
                        if 'telefone' in paciente_data and paciente_data['telefone']:
                            try:
                                paciente_data['telefone'] = decrypt_data(paciente_data['telefone'])
                            except Exception as e:
                                logger.error(f"Erro ao descriptografar telefone do paciente {paciente_id}: {e}")
                                paciente_data['telefone'] = "[Erro na descriptografia]"
                        
                        # Adicionar dados do paciente ao relatório
                        relatorio_data["paciente"] = paciente_data
                    else:
                        logger.warning(f"Paciente {paciente_id} não encontrado")
                        relatorio_data["paciente"] = {"nome": "[Paciente não encontrado]"}
                        
                except Exception as e:
                    logger.error(f"Erro ao buscar dados do paciente {paciente_id}: {e}")
                    relatorio_data["paciente"] = {"nome": "[Erro ao carregar paciente]"}
            else:
                relatorio_data["paciente"] = {"nome": "[ID do paciente não informado]"}
            
            relatorios.append(relatorio_data)
        
        # Ordenar por data de avaliação (mais recentes primeiro)
        relatorios.sort(key=lambda x: x.get('data_avaliacao', datetime.min), reverse=True)
        
        logger.info(f"Retornando {len(relatorios)} relatórios do histórico")
        return relatorios
        
    except Exception as e:
        logger.error(f"Erro ao listar histórico de relatórios do médico {medico_id}: {e}")
        return []


# =================================================================================
# ATUALIZAÇÃO DE PERFIL DO USUÁRIO
# =================================================================================

def atualizar_perfil_usuario(db: firestore.client, user_id: str, negocio_id: str, update_data: schemas.UserProfileUpdate, profile_image_url: Optional[str] = None) -> Optional[Dict]:
    """
    Atualiza o perfil do usuário com validações de segurança.
    
    Args:
        db: Cliente Firestore
        user_id: ID do usuário autenticado
        negocio_id: ID do negócio
        update_data: Dados para atualização
        
    Returns:
        Dados atualizados do usuário ou None se não encontrado
    """
    try:
        logger.info(f"Atualizando perfil do usuário {user_id} no negócio {negocio_id}")
        
        # Buscar usuário no Firestore
        user_ref = db.collection('usuarios').document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            logger.warning(f"Usuário {user_id} não encontrado")
            return None
            
        user_data = user_doc.to_dict()
        
        # Verificar se usuário pertence ao negócio
        user_roles = user_data.get('roles', {})
        if negocio_id not in user_roles:
            logger.warning(f"Usuário {user_id} não pertence ao negócio {negocio_id}")
            return None
        
        # Preparar dados para atualização
        update_dict = {}
        
        # Nome (obrigatório e sempre criptografado)
        if update_data.nome:
            update_dict['nome'] = encrypt_data(update_data.nome.strip())
        
        # Telefone (opcional, criptografado se fornecido)
        if update_data.telefone is not None:
            if update_data.telefone.strip():
                # Validação básica do telefone
                telefone_limpo = ''.join(filter(str.isdigit, update_data.telefone))
                if len(telefone_limpo) >= 10:  # DDD + número
                    update_dict['telefone'] = encrypt_data(update_data.telefone.strip())
                else:
                    raise ValueError("Telefone deve conter pelo menos 10 dígitos (DDD + número)")
            else:
                update_dict['telefone'] = None
        
        # Endereço (opcional, criptografado se fornecido)
        if update_data.endereco is not None:
            endereco_dict = update_data.endereco.model_dump()
            # Criptografar campos sensíveis do endereço
            endereco_criptografado = {}
            for campo, valor in endereco_dict.items():
                if valor and isinstance(valor, str) and valor.strip():
                    if campo == 'cep':
                        # Validação básica do CEP
                        cep_limpo = ''.join(filter(str.isdigit, valor))
                        if len(cep_limpo) != 8:
                            raise ValueError("CEP deve conter exatamente 8 dígitos")
                        endereco_criptografado[campo] = encrypt_data(valor.strip())
                    else:
                        endereco_criptografado[campo] = encrypt_data(valor.strip())
                else:
                    endereco_criptografado[campo] = valor
            update_dict['endereco'] = endereco_criptografado
        
        # URL da imagem de perfil (se fornecida)
        if profile_image_url is not None:
            update_dict['profile_image_url'] = profile_image_url
        
        # Adicionar timestamp de atualização
        update_dict['updated_at'] = firestore.SERVER_TIMESTAMP
        
        # SEGURANÇA: Garantir que firebase_uid nunca seja perdido
        firebase_uid = user_data.get('firebase_uid')
        if firebase_uid and 'firebase_uid' not in update_dict:
            update_dict['firebase_uid'] = firebase_uid
        
        # Executar atualização
        user_ref.update(update_dict)
        logger.info(f"Perfil do usuário {user_id} atualizado com sucesso")
        
        # Buscar dados atualizados
        updated_doc = user_ref.get()
        updated_data = updated_doc.to_dict()
        updated_data['id'] = updated_doc.id
        
        # VERIFICAÇÃO: Confirmar que firebase_uid ainda existe
        if not updated_data.get('firebase_uid'):
            logger.error(f"CRITICAL: firebase_uid perdido para usuário {user_id}")
            # Restaurar firebase_uid se perdido
            if firebase_uid:
                user_ref.update({'firebase_uid': firebase_uid})
                updated_data['firebase_uid'] = firebase_uid
        
        # Descriptografar dados para resposta
        if 'nome' in updated_data and updated_data['nome']:
            try:
                updated_data['nome'] = decrypt_data(updated_data['nome'])
            except Exception as e:
                logger.error(f"Erro ao descriptografar nome: {e}")
                updated_data['nome'] = "[Erro na descriptografia]"
        
        if 'telefone' in updated_data and updated_data['telefone']:
            try:
                updated_data['telefone'] = decrypt_data(updated_data['telefone'])
            except Exception as e:
                logger.error(f"Erro ao descriptografar telefone: {e}")
                updated_data['telefone'] = "[Erro na descriptografia]"
        
        if 'endereco' in updated_data and updated_data['endereco']:
            endereco_descriptografado = {}
            for campo, valor in updated_data['endereco'].items():
                if valor and isinstance(valor, str) and valor.strip():
                    try:
                        endereco_descriptografado[campo] = decrypt_data(valor)
                    except Exception as e:
                        logger.error(f"Erro ao descriptografar campo {campo} do endereço: {e}")
                        endereco_descriptografado[campo] = "[Erro na descriptografia]"
                else:
                    endereco_descriptografado[campo] = valor
            updated_data['endereco'] = endereco_descriptografado
        
        return updated_data
        
    except ValueError as ve:
        logger.warning(f"Erro de validação ao atualizar perfil do usuário {user_id}: {ve}")
        raise
    except Exception as e:
        logger.error(f"Erro ao atualizar perfil do usuário {user_id}: {e}")
        return None


def processar_imagem_base64(base64_data: str, user_id: str) -> Optional[str]:
    """
    Processa imagem Base64 e salva no Google Cloud Storage.
    
    Args:
        base64_data: Dados da imagem em Base64
        user_id: ID do usuário
        
    Returns:
        URL da imagem salva ou None se erro
    """
    try:
        import base64
        import os
        from datetime import datetime
        from google.cloud import storage
        
        # Validar formato Base64
        if not base64_data.startswith('data:image/'):
            raise ValueError("Formato de imagem Base64 inválido")
        
        # Extrair tipo de imagem e dados
        header, encoded_data = base64_data.split(',', 1)
        image_type = header.split('/')[1].split(';')[0]
        
        if image_type not in ['jpeg', 'jpg', 'png']:
            raise ValueError("Tipo de imagem não suportado. Use JPEG ou PNG")
        
        # Decodificar Base64
        image_data = base64.b64decode(encoded_data)
        
        # Verificar tamanho (máximo 5MB)
        if len(image_data) > 5 * 1024 * 1024:
            raise ValueError("Imagem muito grande. Máximo 5MB")
        
        # Gerar nome único para o arquivo
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"profile_{user_id}_{timestamp}.{image_type}"
        
        # Configurar Google Cloud Storage
        bucket_name = os.getenv('CLOUD_STORAGE_BUCKET_NAME', 'barbearia-app-fotoss')
        
        try:
            # Tentar usar Google Cloud Storage
            client = storage.Client()
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(f"profiles/{filename}")
            
            # Upload da imagem
            blob.upload_from_string(image_data, content_type=f"image/{image_type}")
            
            # Tornar o arquivo público
            blob.make_public()
            
            # URL pública do arquivo
            image_url = blob.public_url
            
            logger.info(f"Imagem salva no Cloud Storage para usuário {user_id}: {image_url}")
            return image_url
            
        except Exception as storage_error:
            logger.warning(f"Falha no Cloud Storage, usando fallback local: {storage_error}")
            
            # Fallback: salvar localmente (para desenvolvimento)
            upload_dir = "uploads/profiles"
            os.makedirs(upload_dir, exist_ok=True)
            
            # Salvar arquivo localmente
            file_path = os.path.join(upload_dir, filename)
            with open(file_path, 'wb') as f:
                f.write(image_data)
            
            # URL local
            base_url = "https://barbearia-backend-service-862082955632.southamerica-east1.run.app"
            image_url = f"{base_url}/uploads/profiles/{filename}"
            
            logger.info(f"Imagem salva localmente para usuário {user_id}: {file_path} -> {image_url}")
            return image_url
        
    except Exception as e:
        logger.error(f"Erro ao processar imagem Base64 para usuário {user_id}: {e}")
        return None

# Em crud.py

# =================================================================================
# CRUD DE TAREFAS ESSENCIAIS (PLANO DE AÇÃO)
# =================================================================================

def _agendar_verificacao_tarefa_atrasada(db: firestore.client, tarefa: Dict):
    """
    Cria um documento em 'tarefas_a_verificar' para ser processado por um worker externo (Cloud Function).
    """
    try:
        doc_ref = db.collection('tarefas_a_verificar').document(tarefa['id'])
        doc_ref.set({
            "tarefaId": tarefa['id'],
            "pacienteId": tarefa['pacienteId'],
            "negocioId": tarefa['negocioId'],
            "criadoPorId": tarefa['criadoPorId'],
            "dataHoraLimite": tarefa['dataHoraLimite'],
            "status": "pendente" # O worker mudará para "processado" ou "notificado"
        })
        logger.info(f"Verificação de atraso agendada para tarefa {tarefa['id']}.")
    except Exception as e:
        logger.error(f"Falha ao agendar verificação de tarefa atrasada: {e}")


def criar_tarefa(db: firestore.client, paciente_id: str, negocio_id: str, tarefa_data: schemas.TarefaAgendadaCreate, criador: schemas.UsuarioProfile) -> Dict:
    """Cria uma nova tarefa essencial para um paciente."""
    tarefa_dict = {
        "pacienteId": paciente_id,
        "negocioId": negocio_id,
        "descricao": tarefa_data.descricao,
        "dataHoraLimite": tarefa_data.dataHoraLimite,
        "criadoPorId": criador.id,
        "foiConcluida": False,
        "dataConclusao": None,
        "executadoPorId": None
    }
    
    doc_ref = db.collection('tarefas_essenciais').document()
    doc_ref.set(tarefa_dict)
    
    tarefa_dict['id'] = doc_ref.id
    
    # Agenda a verificação de atraso
    _agendar_verificacao_tarefa_atrasada(db, tarefa_dict)
    
    return tarefa_dict

# Em crud.py, substitua esta função

# Em crud.py, substitua esta função

def listar_tarefas_por_paciente(db: firestore.client, paciente_id: str, status: Optional[schemas.StatusTarefaEnum]) -> List[Dict]:
    """Lista tarefas de um paciente, com filtro opcional por status."""
    query = db.collection('tarefas_essenciais').where('pacienteId', '==', paciente_id).order_by('dataHoraLimite', direction=firestore.Query.ASCENDING)
    
    tarefas = []
    # --- INÍCIO DA CORREÇÃO ---
    # Adiciona o fuso horário UTC à data atual para garantir uma comparação justa
    now = datetime.now(timezone.utc)
    # --- FIM DA CORREÇÃO ---
    
    user_cache = {}

    for doc in query.stream():
        data = doc.to_dict()
        data['id'] = doc.id
        
        # Lógica de filtro de status
        is_concluida = data.get('foiConcluida', False)
        
        # Garante que a data do Firestore é offset-aware antes de comparar
        data_limite = data.get('dataHoraLimite')
        if data_limite and data_limite.tzinfo is None:
            data_limite = data_limite.replace(tzinfo=timezone.utc)

        is_atrasada = not is_concluida and data_limite < now

        if status:
            if status == 'pendente' and (is_concluida or is_atrasada):
                continue
            if status == 'concluida' and not is_concluida:
                continue
            if status == 'atrasada' and not is_atrasada:
                continue
        
        # Enriquecer com dados do criador e executor
        for user_field, user_id in [("criadoPor", data.get("criadoPorId")), ("executadoPor", data.get("executadoPorId"))]:
            if user_id:
                if user_id not in user_cache:
                    user_doc = db.collection('usuarios').document(user_id).get()
                    if user_doc.exists:
                        user_data = user_doc.to_dict()
                        user_cache[user_id] = {
                            "id": user_id,
                            "nome": decrypt_data(user_data.get('nome','')),
                            "email": user_data.get('email', '')
                        }
                if user_id in user_cache:
                    data[user_field] = user_cache[user_id]

        tarefas.append(data)
        
    return tarefas


def marcar_tarefa_como_concluida(db: firestore.client, tarefa_id: str, tecnico: schemas.UsuarioProfile) -> Optional[Dict]:
    """Marca uma tarefa como concluída e dispara a notificação."""
    tarefa_ref = db.collection('tarefas_essenciais').document(tarefa_id)
    tarefa_doc = tarefa_ref.get()

    if not tarefa_doc.exists:
        return None
    
    tarefa_data = tarefa_doc.to_dict()
    if tarefa_data.get('foiConcluida'): # Já foi concluída
        return tarefa_data

    # Atualiza a tarefa
    update_data = {
        "foiConcluida": True,
        "dataConclusao": datetime.utcnow(),
        "executadoPorId": tecnico.id
    }
    tarefa_ref.update(update_data)
    
    # Atualiza o dicionário para a notificação
    tarefa_data.update(update_data)
    tarefa_data['id'] = tarefa_id

    # Dispara a notificação de conclusão
    _notificar_tarefa_concluida(db, tarefa_data)
    
    # Remove a verificação de atraso agendada
    db.collection('tarefas_a_verificar').document(tarefa_id).delete()
    
    # Retorna o documento completo e atualizado
    updated_doc = tarefa_ref.get().to_dict()
    updated_doc['id'] = tarefa_id
    return updated_doc

# =================================================================================
# NOVAS FUNÇÕES DE NOTIFICAÇÃO (SETEMBRO 2025)
# =================================================================================

def _notificar_medico_novo_relatorio(db: firestore.client, relatorio: Dict):
    """Notifica o médico vinculado sobre um novo relatório pendente de avaliação."""
    try:
        medico_id = relatorio.get('medico_id')
        paciente_id = relatorio.get('paciente_id')
        criado_por_id = relatorio.get('criado_por_id')

        if not medico_id or not paciente_id or not criado_por_id:
            logger.warning(f"Dados insuficientes no relatório {relatorio.get('id')} para notificar o médico.")
            return

        medico_doc = db.collection('usuarios').document(medico_id).get()
        if not medico_doc.exists:
            logger.error(f"Médico {medico_id} não encontrado para notificação.")
            return
        medico_data = medico_doc.to_dict()
        tokens_fcm = medico_data.get('fcm_tokens', [])

        paciente_doc = db.collection('usuarios').document(paciente_id).get()
        nome_paciente = decrypt_data(paciente_doc.to_dict().get('nome', '')) if paciente_doc.exists else "Paciente"
        
        criador_doc = db.collection('usuarios').document(criado_por_id).get()
        nome_criador = decrypt_data(criador_doc.to_dict().get('nome', '')) if criador_doc.exists else "A equipe"

        titulo = "Novo Relatório para Avaliação"
        corpo = f"{nome_criador} criou um novo relatório para o paciente {nome_paciente} que precisa da sua avaliação."
        
        # CORREÇÃO: 'title' e 'body' removidos daqui
        data_payload = {
            "tipo": "NOVO_RELATORIO_MEDICO",
            "relatorio_id": relatorio.get('id'),
            "paciente_id": paciente_id,
        }

        db.collection('usuarios').document(medico_id).collection('notificacoes').add({
            "title": titulo, "body": corpo, "tipo": "NOVO_RELATORIO_MEDICO",
            "relacionado": { "relatorio_id": relatorio.get('id'), "paciente_id": paciente_id },
            "lida": False, "data_criacao": firestore.SERVER_TIMESTAMP,
            "dedupe_key": f"NOVO_RELATORIO_{relatorio.get('id')}"
        })

        if tokens_fcm:
            _send_data_push_to_tokens(db, medico_data.get('firebase_uid'), tokens_fcm, data_payload, titulo, corpo, "[Novo Relatório]")
            logger.info(f"Notificação de novo relatório enviada para o médico {medico_id}.")

    except Exception as e:
        logger.error(f"Erro ao notificar médico sobre novo relatório: {e}")


def _notificar_enfermeiro_novo_registro_diario(db: firestore.client, registro: Dict):
    """Notifica o enfermeiro responsável sobre um novo registro diário feito por um técnico."""
    try:
        paciente_id = registro.get('paciente_id')
        tecnico_id = registro.get('tecnico_id')

        if not paciente_id or not tecnico_id:
            logger.warning(f"Dados insuficientes no registro {registro.get('id')} para notificar o enfermeiro.")
            return

        paciente_doc = db.collection('usuarios').document(paciente_id).get()
        if not paciente_doc.exists:
            logger.error(f"Paciente {paciente_id} não encontrado.")
            return
        paciente_data = paciente_doc.to_dict()
        enfermeiro_id = paciente_data.get('enfermeiro_id')
        nome_paciente = decrypt_data(paciente_data.get('nome', ''))

        if not enfermeiro_id:
            logger.info(f"Paciente {paciente_id} não possui enfermeiro vinculado. Nenhuma notificação enviada.")
            return

        enfermeiro_doc = db.collection('usuarios').document(enfermeiro_id).get()
        if not enfermeiro_doc.exists:
            logger.error(f"Enfermeiro {enfermeiro_id} não encontrado.")
            return
        enfermeiro_data = enfermeiro_doc.to_dict()
        tokens_fcm = enfermeiro_data.get('fcm_tokens', [])
        
        tecnico_doc = db.collection('usuarios').document(tecnico_id).get()
        nome_tecnico = decrypt_data(tecnico_doc.to_dict().get('nome', '')) if tecnico_doc.exists else "Um técnico"

        titulo = "Novo Registro no Diário"
        corpo = f"{nome_tecnico} adicionou um novo registro no diário do paciente {nome_paciente}."
        
        # CORREÇÃO: 'title' e 'body' removidos daqui
        data_payload = {
            "tipo": "NOVO_REGISTRO_DIARIO",
            "registro_id": registro.get('id'),
            "paciente_id": paciente_id,
        }

        db.collection('usuarios').document(enfermeiro_id).collection('notificacoes').add({
            "title": titulo, "body": corpo, "tipo": "NOVO_REGISTRO_DIARIO",
            "relacionado": { "registro_id": registro.get('id'), "paciente_id": paciente_id },
            "lida": False, "data_criacao": firestore.SERVER_TIMESTAMP,
            "dedupe_key": f"NOVO_REGISTRO_{registro.get('id')}"
        })

        if tokens_fcm:
            _send_data_push_to_tokens(db, enfermeiro_data.get('firebase_uid'), tokens_fcm, data_payload, titulo, corpo, "[Novo Registro Diário]")
            logger.info(f"Notificação de novo registro diário enviada para o enfermeiro {enfermeiro_id}.")

    except Exception as e:
        logger.error(f"Erro ao notificar enfermeiro sobre novo registro diário: {e}")
    


# Em crud.py, adicione esta função ao final

def _notificar_tarefa_concluida(db: firestore.client, tarefa: Dict):
    """Notifica o criador da tarefa (Enfermeiro) que ela foi concluída por um técnico."""
    try:
        criador_id = tarefa.get('criadoPorId')
        tecnico_id = tarefa.get('executadoPorId')
        paciente_id = tarefa.get('pacienteId')

        if not all([criador_id, tecnico_id, paciente_id]):
            logger.warning(f"Dados insuficientes na tarefa {tarefa.get('id')} para notificar conclusão.")
            return

        criador_doc = db.collection('usuarios').document(criador_id).get()
        if not criador_doc.exists:
            logger.error(f"Criador da tarefa {criador_id} não encontrado.")
            return
        criador_data = criador_doc.to_dict()
        tokens_fcm = criador_data.get('fcm_tokens', [])
        
        tecnico_doc = db.collection('usuarios').document(tecnico_id).get()
        nome_tecnico = decrypt_data(tecnico_doc.to_dict().get('nome', '')) if tecnico_doc.exists else "O técnico"
        
        paciente_doc = db.collection('usuarios').document(paciente_id).get()
        nome_paciente = decrypt_data(paciente_doc.to_dict().get('nome', '')) if paciente_doc.exists else "o paciente"

        titulo = "Tarefa Concluída!"
        corpo = f"{nome_tecnico} concluiu a tarefa '{tarefa.get('descricao', '')[:30]}...' para {nome_paciente}."
        
        # CORREÇÃO: 'title' e 'body' removidos daqui
        data_payload = {
            "tipo": "TAREFA_CONCLUIDA",
            "tarefa_id": tarefa.get('id'),
            "paciente_id": paciente_id,
        }

        db.collection('usuarios').document(criador_id).collection('notificacoes').add({
            "title": titulo, "body": corpo, "tipo": "TAREFA_CONCLUIDA",
            "relacionado": { "tarefa_id": tarefa.get('id'), "paciente_id": paciente_id },
            "lida": False, "data_criacao": firestore.SERVER_TIMESTAMP,
            "dedupe_key": f"TAREFA_CONCLUIDA_{tarefa.get('id')}"
        })

        if tokens_fcm:
            _send_data_push_to_tokens(db, criador_data.get('firebase_uid'), tokens_fcm, data_payload, titulo, corpo, "[Tarefa Concluída]")
            logger.info(f"Notificação de tarefa concluída enviada para {criador_id}.")

    except Exception as e:
        logger.error(f"Erro ao notificar tarefa concluída: {e}")



# Em crud.py, adicione esta função de notificação

def _notificar_tarefa_atrasada(db: firestore.client, tarefa_a_verificar: Dict):
    """Notifica o criador sobre uma tarefa que não foi concluída no prazo."""
    try:
        criador_id = tarefa_a_verificar.get('criadoPorId')
        paciente_id = tarefa_a_verificar.get('pacienteId')
        tarefa_id = tarefa_a_verificar.get('tarefaId')

        if not all([criador_id, paciente_id, tarefa_id]):
            logger.warning("Dados insuficientes no registro de verificação para notificar atraso.")
            return

        tarefa_doc = db.collection('tarefas_essenciais').document(tarefa_id).get()
        if not tarefa_doc.exists:
            logger.error(f"Tarefa original {tarefa_id} não encontrada para notificação de atraso.")
            return
        
        descricao_tarefa = tarefa_doc.to_dict().get('descricao', 'Nome da tarefa não encontrado')
        
        criador_doc = db.collection('usuarios').document(criador_id).get()
        if not criador_doc.exists:
            return
        criador_data = criador_doc.to_dict()
        tokens_fcm = criador_data.get('fcm_tokens', [])
        
        try:
            paciente_doc = db.collection('usuarios').document(paciente_id).get()
            if paciente_doc.exists:
                nome_raw = paciente_doc.to_dict().get('nome', '')
                nome_paciente = decrypt_data(nome_raw) if nome_raw else "o paciente"
            else:
                nome_paciente = "o paciente"
        except Exception as e:
            logger.warning(f"Erro ao buscar nome do paciente {paciente_id}: {e}")
            nome_paciente = "o paciente"

        titulo = "Alerta: Tarefa Atrasada!"
        corpo = f"A tarefa '{descricao_tarefa[:30]}...' para o paciente {nome_paciente} não foi concluída até o prazo final."
        
        # CORREÇÃO: 'title' e 'body' removidos daqui
        data_payload = {
            "tipo": "TAREFA_ATRASADA",
            "tarefa_id": tarefa_id,
            "paciente_id": paciente_id,
        }

        db.collection('usuarios').document(criador_id).collection('notificacoes').add({
            "title": titulo, "body": corpo, "tipo": "TAREFA_ATRASADA",
            "relacionado": { "tarefa_id": tarefa_id, "paciente_id": paciente_id },
            "lida": False, "data_criacao": firestore.SERVER_TIMESTAMP,
            "dedupe_key": f"TAREFA_ATRASADA_{tarefa_id}"
        })

        if tokens_fcm:
            _send_data_push_to_tokens(db, criador_data.get('firebase_uid'), tokens_fcm, data_payload, titulo, corpo, "[Tarefa Atrasada]")
            logger.info(f"Notificação de tarefa atrasada ({tarefa_id}) enviada para {criador_id}.")

    except Exception as e:
        logger.error(f"Erro ao notificar tarefa atrasada: {e}")


def processar_tarefas_atrasadas(db: firestore.client) -> Dict:
    """
    Busca e processa tarefas cuja data limite já passou e que ainda não foram concluídas.
    Esta função é projetada para ser chamada por um job agendado (Cloud Scheduler).
    """
    stats = {"total_verificadas": 0, "total_notificadas": 0, "erros": 0}
    
    # --- INÍCIO DA CORREÇÃO ---
    # Garante que a data/hora atual tenha o fuso horário UTC para comparação
    now = datetime.now(timezone.utc)
    # --- FIM DA CORREÇÃO ---
    
    # 1. Busca registros de verificação que estão pendentes e cujo prazo já venceu
    verificacao_ref = db.collection('tarefas_a_verificar')
    query = verificacao_ref.where('status', '==', 'pendente').where('dataHoraLimite', '<=', now)
    
    tarefas_para_verificar = list(query.stream())
    stats["total_verificadas"] = len(tarefas_para_verificar)
    
    if not tarefas_para_verificar:
        logger.info("Nenhuma tarefa atrasada para processar.")
        return stats

    for doc_verificacao in tarefas_para_verificar:
        try:
            dados_verificacao = doc_verificacao.to_dict()
            tarefa_id = dados_verificacao.get('tarefaId')

            # 2. Verifica o status atual da tarefa original
            tarefa_ref = db.collection('tarefas_essenciais').document(tarefa_id)
            tarefa_doc = tarefa_ref.get()

            if tarefa_doc.exists and not tarefa_doc.to_dict().get('foiConcluida'):
                # 3. Se não foi concluída, dispara a notificação
                _notificar_tarefa_atrasada(db, dados_verificacao)
                stats["total_notificadas"] += 1
            
            # 4. Marca o registro como processado para não notificar novamente
            doc_verificacao.reference.update({"status": "processado"})

        except Exception as e:
            stats["erros"] += 1
            logger.error(f"Erro ao processar verificação da tarefa {doc_verificacao.id}: {e}")
            # Marca como erro para possível re-tentativa manual
            doc_verificacao.reference.update({"status": "erro", "mensagem_erro": str(e)})

    logger.info(f"Processamento de tarefas atrasadas concluído: {stats}")
    return stats



# NOVAS NOTIFICAÇÕES INSTANTÂNEAS (SETEMBRO 2025)
# ================================================================================

def _notificar_paciente_exame_criado(db: firestore.client, paciente_id: str, exame_data: Dict):
    """Notifica o paciente sobre um novo exame criado para ele."""
    try:
        paciente_doc_ref = db.collection('usuarios').document(paciente_id)
        paciente_doc = paciente_doc_ref.get()

        if not paciente_doc.exists:
            logger.error(f"Paciente {paciente_id} não encontrado para notificação de exame.")
            return

        paciente_data = paciente_doc.to_dict()
        nome_exame = exame_data.get('nome_exame', 'exame')

        # Melhorar a mensagem do exame
        mensagem_body = f"Foi agendado o exame '{nome_exame}' para você."

        # 1. Persistir notificação no Firestore
        exame_id = exame_data.get('id', 'novo_exame')
        notificacao_id = f"EXAME_CRIADO:{exame_id}"

        paciente_doc_ref.collection('notificacoes').document(notificacao_id).set({
            "title": "Novo Exame Agendado",
            "body": mensagem_body,
            "tipo": "EXAME_CRIADO",
            "relacionado": {"exame_id": exame_id, "paciente_id": paciente_id},
            "lida": False,
            "data_criacao": firestore.SERVER_TIMESTAMP,
            "dedupe_key": notificacao_id
        })

        logger.info(f"Notificação de exame criado PERSISTIDA para paciente {paciente_id}")

        # 2. Enviar FCM push notification
        fcm_tokens = paciente_data.get('fcm_tokens', [])
        if fcm_tokens:
            try:
                from firebase_admin import messaging

                data_payload = {
                    "tipo": "EXAME_CRIADO",
                    "exame_id": exame_id,
                    "paciente_id": paciente_id
                }

                message = messaging.MulticastMessage(
                    notification=messaging.Notification(
                        title="Novo Exame Agendado",
                        body=mensagem_body
                    ),
                    data=data_payload,
                    tokens=fcm_tokens
                )

                response = messaging.send_multicast(message)
                logger.info(f"Push notification de exame enviada: {response.success_count}/{len(fcm_tokens)} tokens")

            except Exception as e:
                logger.error(f"Erro ao enviar push notification de exame: {e}")
        else:
            logger.warning(f"Paciente {paciente_id} não possui tokens FCM")

    except Exception as e:
        logger.error(f"Erro ao notificar exame criado para paciente {paciente_id}: {e}")


def _notificar_paciente_suporte_adicionado(db: firestore.client, paciente_id: str, suporte_data: Dict):
    """Notifica o paciente sobre um novo suporte psicológico adicionado."""
    try:
        paciente_doc_ref = db.collection('usuarios').document(paciente_id)
        paciente_doc = paciente_doc_ref.get()

        if not paciente_doc.exists:
            logger.error(f"Paciente {paciente_id} não encontrado para notificação de suporte.")
            return

        paciente_data = paciente_doc.to_dict()

        # Mensagem genérica para evitar problemas com criptografia
        mensagem_body = "Um novo suporte psicológico foi postado para você."

        # 1. Persistir notificação no Firestore
        suporte_id = suporte_data.get('id', 'novo_suporte')
        notificacao_id = f"SUPORTE_ADICIONADO:{suporte_id}"

        paciente_doc_ref.collection('notificacoes').document(notificacao_id).set({
            "title": "Novo Suporte Psicológico",
            "body": mensagem_body,
            "tipo": "SUPORTE_ADICIONADO",
            "relacionado": {"suporte_id": suporte_id, "paciente_id": paciente_id},
            "lida": False,
            "data_criacao": firestore.SERVER_TIMESTAMP,
            "dedupe_key": notificacao_id
        })

        logger.info(f"Notificação de suporte adicionado PERSISTIDA para paciente {paciente_id}")

        # 2. Enviar FCM push notification
        fcm_tokens = paciente_data.get('fcm_tokens', [])
        if fcm_tokens:
            try:
                from firebase_admin import messaging

                data_payload = {
                    "tipo": "SUPORTE_ADICIONADO",
                    "suporte_id": suporte_id,
                    "paciente_id": paciente_id
                }

                message = messaging.MulticastMessage(
                    notification=messaging.Notification(
                        title="Novo Suporte Psicológico",
                        body=mensagem_body
                    ),
                    data=data_payload,
                    tokens=fcm_tokens
                )

                response = messaging.send_multicast(message)
                logger.info(f"Push notification de suporte enviada: {response.success_count}/{len(fcm_tokens)} tokens")

            except Exception as e:
                logger.error(f"Erro ao enviar push notification de suporte: {e}")
        else:
            logger.warning(f"Paciente {paciente_id} não possui tokens FCM")

    except Exception as e:
        logger.error(f"Erro ao notificar suporte adicionado para paciente {paciente_id}: {e}")


def processar_lembretes_exames(db: firestore.client) -> Dict:
    """
    Busca exames marcados para amanhã e envia lembretes para os pacientes.
    Esta função é projetada para ser chamada por um job agendado (Cloud Scheduler).
    """
    stats = {"total_exames_verificados": 0, "total_lembretes_enviados": 0, "erros": 0}
    
    from datetime import timezone, timedelta
    
    amanha = datetime.now(timezone.utc) + timedelta(days=1)
    data_amanha_inicio = amanha.replace(hour=0, minute=0, second=0, microsecond=0)
    data_amanha_fim = amanha.replace(hour=23, minute=59, second=59, microsecond=999999)

    logger.info(f"Processando lembretes para exames entre {data_amanha_inicio} e {data_amanha_fim}")

    try:
        usuarios_ref = db.collection('usuarios')

        for usuario_doc in usuarios_ref.stream():
            usuario_id = usuario_doc.id

            exames_ref = usuario_doc.reference.collection('exames')
            query = exames_ref.where('data_exame', '>=', data_amanha_inicio).where('data_exame', '<=', data_amanha_fim)

            exames_amanha = list(query.stream())
            stats["total_exames_verificados"] += len(exames_amanha)

            if exames_amanha:
                try:
                    usuario_data = usuario_doc.to_dict()
                    nome_paciente_raw = usuario_data.get('nome', '')
                    nome_paciente = decrypt_data(nome_paciente_raw) if nome_paciente_raw else "Paciente"
                    tokens_fcm = usuario_data.get('fcm_tokens', [])

                    for exame_doc in exames_amanha:
                        try:
                            exame_data = exame_doc.to_dict()
                            nome_exame = exame_data.get('nome_exame', 'Exame')
                            horario_exame = exame_data.get('horario_exame', '')

                            horario_texto = f" às {horario_exame}" if horario_exame else ""
                            mensagem_title = "Lembrete de Exame"
                            mensagem_body = f"Olá {nome_paciente}! Você tem o exame '{nome_exame}' marcado para amanhã{horario_texto}."

                            notificacao_id = f"LEMBRETE_EXAME:{exame_doc.id}:{data_amanha_inicio.strftime('%Y%m%d')}"

                            try:
                                notificacao_doc_ref = usuario_doc.reference.collection('notificacoes').document(notificacao_id)

                                if not notificacao_doc_ref.get().exists:
                                    notificacao_doc_ref.set({
                                        "title": mensagem_title,
                                        "body": mensagem_body,
                                        "tipo": "LEMBRETE_EXAME",
                                        "relacionado": {
                                            "exame_id": exame_doc.id,
                                            "paciente_id": usuario_id,
                                            "data_exame": exame_data.get('data_exame')
                                        },
                                        "lida": False,
                                        "data_criacao": firestore.SERVER_TIMESTAMP,
                                        "dedupe_key": notificacao_id
                                    })
                                    logger.info(f"Notificação de lembrete de exame PERSISTIDA para o paciente {usuario_id}.")
                                else:
                                    logger.info(f"Notificação de lembrete já existe para o exame {exame_doc.id}")
                                    continue

                            except Exception as e:
                                logger.error(f"Erro ao PERSISTIR notificação de lembrete de exame: {e}")
                                stats["erros"] += 1
                                continue

                            if tokens_fcm:
                                # CORREÇÃO: 'title' e 'body' removidos daqui
                                data_payload = {
                                    "tipo": "LEMBRETE_EXAME",
                                    "exame_id": exame_doc.id,
                                    "paciente_id": usuario_id,
                                }
                                try:
                                    from firebase_admin import messaging

                                    message = messaging.MulticastMessage(
                                        notification=messaging.Notification(
                                            title=mensagem_title,
                                            body=mensagem_body
                                        ),
                                        data=data_payload,
                                        tokens=tokens_fcm
                                    )

                                    response = messaging.send_multicast(message)
                                    stats["total_lembretes_enviados"] += 1
                                    logger.info(f"Lembrete de exame enviado via FCM para paciente {usuario_id}: {response.success_count}/{len(tokens_fcm)} tokens")
                                except Exception as e:
                                    logger.error(f"Erro ao enviar FCM para lembrete de exame: {e}")
                                    stats["erros"] += 1
                            else:
                                logger.warning(f"Paciente {usuario_id} não possui tokens FCM para receber lembrete")

                        except Exception as e:
                            logger.error(f"Erro ao processar exame {exame_doc.id}: {e}")
                            stats["erros"] += 1

                except Exception as e:
                    logger.error(f"Erro ao processar exames do usuário {usuario_id}: {e}")
                    stats["erros"] += 1

    except Exception as e:
        logger.error(f"Erro geral ao processar lembretes de exames: {e}")
        stats["erros"] += 1

    logger.info(f"Processamento de lembretes de exames concluído: {stats}")
    return stats


def verificar_disponibilidade_profissionais(db: firestore.client) -> Dict:
    """
    FUNÇÃO REMOVIDA: Verifica se há profissionais disponíveis e envia alertas quando necessário.
    Esta função foi desabilitada conforme solicitação do usuário.
    """
    # FUNÇÃO DESABILITADA - retorna stats vazios
    return {"alertas_enviados": 0, "tecnicos_verificados": 0, "enfermeiros_verificados": 0, "medicos_verificados": 0, "erros": 0}


def _enviar_alerta_ausencia(db: firestore.client, negocio_id: str, tipo_alerta: str, mensagem: str):
    """FUNÇÃO REMOVIDA: Envia alerta de ausência para admins do negócio.
    Esta função foi desabilitada conforme solicitação do usuário."""
    # FUNÇÃO DESABILITADA - não faz nada
    return