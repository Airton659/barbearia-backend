# crud/usuarios.py
"""
CRUD para gestão de usuários e autenticação
"""

import logging
from typing import Optional, Dict
from firebase_admin import firestore
import schemas
from crypto_utils import encrypt_data, decrypt_data
from .utils import (
    encrypt_user_sensitive_fields,
    encrypt_endereco_fields,
)

logger = logging.getLogger(__name__)

USER_SENSITIVE_FIELDS = ['nome', 'telefone']

def buscar_usuario_por_firebase_uid(db: firestore.client, firebase_uid: str) -> Optional[Dict]:
    """
    Busca um usuário na coleção 'usuarios' pelo seu firebase_uid e descriptografa os dados sensíveis.
    
    CORREÇÃO CRÍTICA: Se existir múltiplos usuários com mesmo firebase_uid (problema de duplicação),
    retorna o usuário com maior privilégio (admin > profissional > tecnico > medico > cliente).
    """
    try:
        # BUSCAR TODOS os usuários com este firebase_uid (não só limit(1))
        query = db.collection('usuarios').where('firebase_uid', '==', firebase_uid)
        docs = list(query.stream())
        
        if not docs:
            return None
            
        # Se só tem 1 usuário, retornar ele
        if len(docs) == 1:
            user_doc = docs[0].to_dict()
            user_doc['id'] = docs[0].id
        else:
            # PROBLEMA CRÍTICO: Múltiplos usuários com mesmo firebase_uid!
            logger.warning(f"DUPLICAÇÃO DETECTADA: {len(docs)} usuários com firebase_uid {firebase_uid}")
            
            # Definir hierarquia de privilégios (maior para menor)
            role_priority = {
                'admin': 5,
                'profissional': 4, 
                'enfermeiro': 4,  # enfermeiro = profissional
                'tecnico': 3,
                'medico': 2,
                'cliente': 1,
                'platform': 6  # super admin
            }
            
            best_user = None
            best_priority = 0
            
            for doc in docs:
                user_data = doc.to_dict()
                user_data['id'] = doc.id
                
                # Calcular prioridade máxima deste usuário (considerando todos os seus roles)
                user_priority = 0
                roles = user_data.get('roles', {})
                
                for negocio_id, role in roles.items():
                    role_prio = role_priority.get(role, 0)
                    if role_prio > user_priority:
                        user_priority = role_prio
                
                # Se este usuário tem prioridade maior, escolher ele
                if user_priority > best_priority:
                    best_priority = user_priority
                    best_user = user_data
                    
            user_doc = best_user
            logger.info(f"Selecionado usuário {user_doc['id']} com maior privilégio (prioridade {best_priority})")

        # Descriptografa os campos com tratamento de erro individual
        if 'nome' in user_doc and user_doc['nome']:
            try:
                user_doc['nome'] = decrypt_data(user_doc['nome'])
            except Exception as e:
                logger.error(f"Erro ao descriptografar nome do usuário {user_doc.get('id', 'unknown')}: {e}")
                user_doc['nome'] = "[ERRO_DESCRIPTOGRAFIA]"
                
        if 'telefone' in user_doc and user_doc['telefone']:
            try:
                user_doc['telefone'] = decrypt_data(user_doc['telefone'])
            except Exception as e:
                logger.error(f"Erro ao descriptografar telefone do usuário {user_doc.get('id', 'unknown')}: {e}")
                user_doc['telefone'] = "[ERRO_DESCRIPTOGRAFIA]"
                
        if 'endereco' in user_doc and user_doc['endereco']:
            try:
                endereco_descriptografado = {}
                for k, v in user_doc['endereco'].items():
                    if v and isinstance(v, str) and v.strip():
                        try:
                            endereco_descriptografado[k] = decrypt_data(v)
                        except Exception as e:
                            logger.error(f"Erro ao descriptografar endereço.{k} do usuário {user_doc.get('id', 'unknown')}: {e}")
                            endereco_descriptografado[k] = "[ERRO_DESCRIPTOGRAFIA]"
                    else:
                        endereco_descriptografado[k] = v
                user_doc['endereco'] = endereco_descriptografado
            except Exception as e:
                logger.error(f"Erro ao descriptografar endereço completo do usuário {user_doc.get('id', 'unknown')}: {e}")

        logger.info(f"Usuário {user_doc.get('id', 'unknown')} ({firebase_uid}) encontrado e descriptografado com sucesso")
        return user_doc
        
    except Exception as e:
        logger.error(f"ERRO CRÍTICO ao buscar usuário por firebase_uid {firebase_uid}: {e}")
        logger.error(f"Tipo do erro: {type(e).__name__}")
        import traceback
        logger.error(f"Stack trace: {traceback.format_exc()}")
        # NUNCA retornar None - isso causa 404! Tentar busca alternativa
        
        try:
            logger.warning(f"Tentando busca alternativa sem descriptografia para firebase_uid {firebase_uid}")
            # Busca simples sem descriptografia como fallback
            query = db.collection('usuarios').where('firebase_uid', '==', firebase_uid).limit(1)
            docs = list(query.stream())
            if docs:
                user_doc = docs[0].to_dict()
                user_doc['id'] = docs[0].id
                logger.warning(f"FALLBACK: Usuário {user_doc['id']} encontrado sem descriptografia")
                return user_doc
        except Exception as fallback_e:
            logger.error(f"FALLBACK também falhou: {fallback_e}")
            
        return None

def criar_ou_atualizar_usuario(db: firestore.client, user_data: schemas.UsuarioSync) -> Dict:
    """
    Cria ou atualiza um usuário no Firestore, criptografando dados sensíveis.
    Esta função é a única fonte da verdade para a lógica de onboarding.
    """
    # DEBUG: Log dos dados recebidos
    logger.critical(f"🔍 DEBUG NOME - user_data.nome enviado: '{user_data.nome}'")
    logger.critical(f"🔍 DEBUG ENDERECO - user_data: nome={user_data.nome}, telefone={user_data.telefone}, endereco={user_data.endereco}")
    if user_data.endereco:
        logger.critical(f"🔍 DEBUG ENDERECO - endereco.dict(): {user_data.endereco.dict()}")
    else:
        logger.critical(f"🔍 DEBUG ENDERECO - endereco é None ou vazio!")
        
    negocio_id = user_data.negocio_id

    # Criptografa os dados antes de salvar
    nome_criptografado = encrypt_data(user_data.nome)
    telefone_criptografado = encrypt_data(user_data.telefone) if user_data.telefone else None
    endereco_criptografado = None
    if user_data.endereco:
        endereco_criptografado = {}
        for k, v in user_data.endereco.dict().items():
            if v and isinstance(v, str) and v.strip():
                endereco_criptografado[k] = encrypt_data(v)
            else:
                endereco_criptografado[k] = v
        logger.critical(f"🔍 DEBUG ENDERECO - endereco_criptografado: {endereco_criptografado}")
    else:
        logger.critical(f"🔍 DEBUG ENDERECO - Pulando criptografia, endereco é None")

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
            if endereco_criptografado:
                user_dict['endereco'] = endereco_criptografado
            doc_ref = db.collection('usuarios').document()
            doc_ref.set(user_dict)
            user_dict['id'] = doc_ref.id
            logger.info(f"Novo usuário {user_data.email} criado como Super Admin.")
            
            # Descriptografa para retornar ao usuário
            user_dict['nome'] = user_data.nome
            user_dict['telefone'] = user_data.telefone
            if user_data.endereco:
                user_dict['endereco'] = user_data.endereco.dict()
            return user_dict
        else:
            raise ValueError("Não é possível se registrar sem um negócio específico.")
    
    # Fluxo multi-tenant  
    # CORREÇÃO CRÍTICA: Buscar usuário FORA da transação para ver dados já commitados
    user_existente = buscar_usuario_por_firebase_uid(db, user_data.firebase_uid)
    
    @firestore.transactional
    def transaction_sync_user(transaction):
        
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
            # CORREÇÃO CRÍTICA: Se usuário já existe, SEMPRE atualizar dados e retornar
            # NUNCA criar novo usuário duplicado!
            logger.critical(f"🔍 DEBUG NOME - user_existente.nome atual no banco: '{user_existente.get('nome', 'N/A')}'")
            user_ref = db.collection('usuarios').document(user_existente['id'])
            
            # Atualizar dados do usuário existente (nome, email, telefone, endereco podem ter mudado)
            update_data = {}
            if user_data.nome and user_data.nome != user_existente.get('nome', ''):
                logger.critical(f"🔍 DEBUG NOME - Nome será atualizado de '{user_existente.get('nome', '')}' para '{user_data.nome}'")
                update_data['nome'] = nome_criptografado
            else:
                logger.critical(f"🔍 DEBUG NOME - Nome NÃO será atualizado (igual ou vazio): enviado='{user_data.nome}', atual='{user_existente.get('nome', '')}')")
            if user_data.email and user_data.email != user_existente.get('email', ''):
                update_data['email'] = user_data.email
            if user_data.telefone and user_data.telefone != user_existente.get('telefone', ''):
                update_data['telefone'] = telefone_criptografado
            if user_data.endereco and endereco_criptografado:
                # Sempre atualizar endereço se for enviado (pode ter campos diferentes)
                update_data['endereco'] = endereco_criptografado
                logger.critical(f"🔍 DEBUG ENDERECO - Adicionando endereco ao update_data: {endereco_criptografado}")
            else:
                logger.critical(f"🔍 DEBUG ENDERECO - NÃO adicionando endereco (user_data.endereco={user_data.endereco}, endereco_criptografado={endereco_criptografado})")
            
            # Adicionar role se não tiver para este negócio
            if negocio_id not in user_existente.get("roles", {}):
                update_data[f'roles.{negocio_id}'] = role
                user_existente["roles"][negocio_id] = role
                if role == "admin":
                    transaction.update(negocio_doc_ref, {'admin_uid': user_data.firebase_uid})
            
            # Aplicar atualizações se houver alguma
            if update_data:
                transaction.update(user_ref, update_data)
                logger.info(f"Usuário existente {user_existente['id']} atualizado para {user_data.email}")
                
                # Atualizar os valores no objeto de retorno com os novos dados descriptografados
                if 'nome' in update_data:
                    user_existente['nome'] = user_data.nome
                    logger.critical(f"🔍 DEBUG NOME - Nome atualizado no objeto de retorno para: '{user_data.nome}'")
                if 'email' in update_data:
                    user_existente['email'] = user_data.email
                if 'telefone' in update_data:
                    user_existente['telefone'] = user_data.telefone
                if 'endereco' in update_data and user_data.endereco:
                    user_existente['endereco'] = user_data.endereco.dict()
            else:
                logger.info(f"Usuário existente {user_existente['id']} retornado sem alterações para {user_data.email}")
            
            logger.critical(f"🔍 DEBUG NOME - Retornando user_existente com nome: '{user_existente.get('nome', 'N/A')}'")
            return user_existente

        # PROTEÇÃO EXTRA: Fazer busca dupla para garantir que não existe
        # (proteção contra condições de corrida)
        double_check_query = db.collection('usuarios').where('firebase_uid', '==', user_data.firebase_uid).limit(1)
        existing_docs = list(double_check_query.get(transaction=transaction))
        
        if existing_docs:
            logger.warning(f"DOUBLE CHECK: Usuário {user_data.firebase_uid} encontrado na segunda busca! Impedindo criação duplicada.")
            existing_user = existing_docs[0].to_dict()
            existing_user['id'] = existing_docs[0].id
            return existing_user

        # Só criar se realmente não existe
        logger.info(f"Criando NOVO usuário para {user_data.email} com firebase_uid {user_data.firebase_uid}")
        user_dict = {
            "nome": nome_criptografado, 
            "email": user_data.email, 
            "firebase_uid": user_data.firebase_uid,
            "roles": {negocio_id: role}, 
            "fcm_tokens": []
        }
        if telefone_criptografado:
            user_dict['telefone'] = telefone_criptografado
        if endereco_criptografado:
            user_dict['endereco'] = endereco_criptografado
        
        new_user_ref = db.collection('usuarios').document()
        transaction.set(new_user_ref, user_dict)
        user_dict['id'] = new_user_ref.id

        if role == "admin":
            transaction.update(negocio_doc_ref, {'admin_uid': user_data.firebase_uid})
        
        # Descriptografa para retornar ao usuário
        user_dict['nome'] = user_data.nome
        user_dict['telefone'] = user_data.telefone
        if user_data.endereco:
            user_dict['endereco'] = user_data.endereco.dict()

        return user_dict
    
    return transaction_sync_user(db.transaction())

def atualizar_perfil_usuario(db: firestore.client, user_id: str, profile_data: schemas.UsuarioProfileUpdate) -> Dict:
    """
    Atualiza apenas os campos especificados do perfil do usuário.
    """
    logger.critical(f"🔍 DEBUG PROFILE UPDATE - user_id: {user_id}, dados: {profile_data.dict(exclude_unset=True)}")
    
    user_ref = db.collection('usuarios').document(user_id)
    user_doc = user_ref.get()
    
    if not user_doc.exists:
        raise ValueError("Usuário não encontrado")
    
    update_data = {}
    
    # Atualizar nome se fornecido
    if profile_data.nome is not None:
        nome_criptografado = encrypt_data(profile_data.nome)
        update_data['nome'] = nome_criptografado
        logger.critical(f"🔍 DEBUG PROFILE UPDATE - Atualizando nome para: '{profile_data.nome}'")
    
    # Atualizar telefone se fornecido
    if profile_data.telefone is not None:
        telefone_criptografado = encrypt_data(profile_data.telefone)
        update_data['telefone'] = telefone_criptografado
        logger.critical(f"🔍 DEBUG PROFILE UPDATE - Atualizando telefone para: '{profile_data.telefone}'")
    
    # Atualizar endereço se fornecido
    if profile_data.endereco is not None:
        endereco_criptografado = {}
        for k, v in profile_data.endereco.dict().items():
            if v and isinstance(v, str) and v.strip():
                endereco_criptografado[k] = encrypt_data(v)
            else:
                endereco_criptografado[k] = v
        update_data['endereco'] = endereco_criptografado
        logger.critical(f"🔍 DEBUG PROFILE UPDATE - Atualizando endereco")
    
    # Aplicar atualizações
    if update_data:
        user_ref.update(update_data)
        logger.critical(f"🔍 DEBUG PROFILE UPDATE - {len(update_data)} campos atualizados no Firestore")
    else:
        logger.critical(f"🔍 DEBUG PROFILE UPDATE - Nenhum campo para atualizar")
    
    # Buscar dados atualizados e descriptografar
    updated_user = buscar_usuario_por_firebase_uid(db, user_doc.to_dict()['firebase_uid'])
    logger.critical(f"🔍 DEBUG PROFILE UPDATE - Retornando usuário atualizado")
    
    return updated_user

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
        
        # Executar atualização
        user_ref.update(update_dict)
        logger.info(f"Perfil do usuário {user_id} atualizado com sucesso")
        
        # Buscar dados atualizados
        updated_doc = user_ref.get()
        updated_data = updated_doc.to_dict()
        updated_data['id'] = updated_doc.id
        
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
    Processa imagem Base64 e salva localmente (implementação para desenvolvimento).
    
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
        
        # Criar diretório local para salvar as imagens (se não existir)
        upload_dir = "uploads/profiles"
        os.makedirs(upload_dir, exist_ok=True)
        
        # Salvar arquivo localmente
        file_path = os.path.join(upload_dir, filename)
        with open(file_path, 'wb') as f:
            f.write(image_data)
        
        # Retornar URL para servir a imagem
        # Em desenvolvimento, assumindo que há um servidor servindo /uploads/
        base_url = "https://barbearia-backend-service-862082955632.southamerica-east1.run.app"
        image_url = f"{base_url}/uploads/profiles/{filename}"
        
        logger.info(f"Imagem salva para usuário {user_id}: {file_path} -> {image_url}")
        return image_url
        
    except Exception as e:
        logger.error(f"Erro ao processar imagem Base64 para usuário {user_id}: {e}")
        return None