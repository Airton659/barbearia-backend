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
    """Busca um usuário na coleção 'usuarios' pelo seu firebase_uid e descriptografa os dados sensíveis."""
    try:
        query = db.collection('usuarios').where('firebase_uid', '==', firebase_uid).limit(1)
        docs = list(query.stream())
        if docs:
            user_doc = docs[0].to_dict()
            user_doc['id'] = docs[0].id

            # Descriptografa os campos
            if 'nome' in user_doc:
                user_doc['nome'] = decrypt_data(user_doc['nome'])
            if 'telefone' in user_doc and user_doc['telefone']:
                user_doc['telefone'] = decrypt_data(user_doc['telefone'])
            if 'endereco' in user_doc and user_doc['endereco']:
                user_doc['endereco'] = {k: decrypt_data(v) for k, v in user_doc['endereco'].items()}

            return user_doc
        return None
    except Exception as e:
        logger.error(f"Erro ao buscar/descriptografar usuário por firebase_uid {firebase_uid}: {e}")
        # Se a descriptografia falhar (ex: chave errada), não retorna dados corrompidos
        return None

def criar_ou_atualizar_usuario(db: firestore.client, user_data: schemas.UsuarioSync) -> Dict:
    """
    Cria ou atualiza um usuário no Firestore, criptografando dados sensíveis.
    Esta função é a fonte da verdade para a lógica de onboarding, como no backup.
    """
    negocio_id = user_data.negocio_id
    
    # Criptografa os dados antes de salvar
    dados_para_criptografar = {'nome': user_data.nome, 'telefone': user_data.telefone}
    dados_criptografados = encrypt_user_sensitive_fields(dados_para_criptografar, USER_SENSITIVE_FIELDS)
    
    # Fluxo de Super Admin (lógica do backup)
    if not negocio_id:
        if not db.collection('usuarios').limit(1).get():
            user_dict = {
                "nome": dados_criptografados['nome'], "email": user_data.email, "firebase_uid": user_data.firebase_uid,
                "roles": {"platform": "super_admin"}, "fcm_tokens": []
            }
            if dados_criptografados['telefone']:
                user_dict['telefone'] = dados_criptografados['telefone']
            
            doc_ref = db.collection('usuarios').document()
            doc_ref.set(user_dict)
            user_dict['id'] = doc_ref.id
            logger.info(f"Novo usuário {user_data.email} criado como Super Admin.")
            
            user_dict['nome'] = user_data.nome
            user_dict['telefone'] = user_data.telefone
            return user_dict
        else:
            raise ValueError("Não é possível se registrar sem um negócio específico.")
    
    # Fluxo multi-tenant (lógica do backup)
    @firestore.transactional
    def transaction_sync_user(transaction):
        user_existente = buscar_usuario_por_firebase_uid(db, user_data.firebase_uid)
        negocio_doc_ref = db.collection('negocios').document(negocio_id)
        negocio_doc = negocio_doc_ref.get(transaction=transaction)
        
        if not negocio_doc.exists:
            raise ValueError(f"O negócio com ID '{negocio_id}' não foi encontrado.")

        negocio_data = negocio_doc.to_dict()
        role = "cliente"
        has_admin = negocio_data.get('admin_uid') is not None
        
        if not has_admin and user_data.codigo_convite and user_data.codigo_convite == negocio_data.get('codigo_convite'):
            role = "admin"
        
        if user_existente:
            user_ref = db.collection('usuarios').document(user_existente['id'])
            # Atualiza os dados principais se estiverem sendo enviados (lógica de update)
            update_fields = {}
            if user_data.nome:
                update_fields['nome'] = dados_criptografados['nome']
            if user_data.telefone:
                update_fields['telefone'] = dados_criptografados['telefone']
            
            if update_fields:
                 transaction.update(user_ref, update_fields)

            if negocio_id not in user_existente.get("roles", {}):
                transaction.update(user_ref, {f'roles.{negocio_id}': role})
                if role == "admin":
                    transaction.update(negocio_doc_ref, {'admin_uid': user_data.firebase_uid})
            
            # Retorna os dados atualizados (já descriptografados pela busca)
            return buscar_usuario_por_firebase_uid(db, user_data.firebase_uid)
        
        # Criar novo usuário
        user_dict = {
            "nome": dados_criptografados['nome'], "email": user_data.email, "firebase_uid": user_data.firebase_uid,
            "roles": {negocio_id: role}, "fcm_tokens": []
        }
        if dados_criptografados['telefone']:
            user_dict['telefone'] = dados_criptografados['telefone']
        
        new_user_ref = db.collection('usuarios').document()
        transaction.set(new_user_ref, user_dict)
        user_dict['id'] = new_user_ref.id
        
        if role == "admin":
            transaction.update(negocio_doc_ref, {'admin_uid': user_data.firebase_uid})
        
        # Descriptografa para retornar ao usuário
        user_dict['nome'] = user_data.nome
        user_dict['telefone'] = user_data.telefone
        return user_dict
    
    return transaction_sync_user(db.transaction())

def adicionar_fcm_token(db: firestore.client, firebase_uid: str, fcm_token: str):
    """Adiciona um FCM token a um usuário, evitando duplicatas."""
    user_doc = buscar_usuario_por_firebase_uid(db, firebase_uid)
    if user_doc:
        doc_ref = db.collection('usuarios').document(user_doc['id'])
        doc_ref.update({'fcm_tokens': firestore.ArrayUnion([fcm_token])})

def remover_fcm_token(db: firestore.client, firebase_uid: str, fcm_token: str):
    """Remove um FCM token de um usuário."""
    user_doc = buscar_usuario_por_firebase_uid(db, firebase_uid)
    if user_doc:
        doc_ref = db.collection('usuarios').document(user_doc['id'])
        doc_ref.update({'fcm_tokens': firestore.ArrayRemove([fcm_token])})

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