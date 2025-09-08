# crud/pacientes.py
"""
CRUD para gestão de pacientes
"""

import logging
from typing import Optional, List, Dict
from firebase_admin import firestore
import schemas
from .utils import (
    decrypt_user_sensitive_fields,
    encrypt_endereco_fields,
    decrypt_endereco_fields,
    add_timestamps
)

logger = logging.getLogger(__name__)

# Campos sensíveis que precisam de criptografia
USER_SENSITIVE_FIELDS = ['nome', 'telefone']


def listar_pacientes_por_profissional_ou_tecnico(db: firestore.client, negocio_id: str, usuario_id: str, role: str) -> List[Dict]:
    """Lista pacientes acessíveis por um profissional ou técnico."""
    pacientes = []
    try:
        # Buscar usuários com role 'cliente' no negócio
        query = db.collection('usuarios').where(f'roles.{negocio_id}', '==', 'cliente')
        
        for doc in query.stream():
            paciente_data = doc.to_dict()
            paciente_data['id'] = doc.id
            
            # Verificar se está ativo no negócio
            status_por_negocio = paciente_data.get('status_por_negocio', {})
            user_status = status_por_negocio.get(negocio_id, 'ativo')
            
            if user_status == 'ativo':
                # Descriptografar dados sensíveis
                paciente_data = decrypt_user_sensitive_fields(paciente_data, USER_SENSITIVE_FIELDS)
                
                if 'endereco' in paciente_data and paciente_data['endereco']:
                    paciente_data['endereco'] = decrypt_endereco_fields(paciente_data['endereco'])
                
                pacientes.append(paciente_data)
        
        logger.info(f"Retornando {len(pacientes)} pacientes para {role} {usuario_id} no negócio {negocio_id}")
        return pacientes
    except Exception as e:
        logger.error(f"Erro ao listar pacientes para {role} {usuario_id}: {e}")
        return []


def atualizar_dados_pessoais_paciente(db: firestore.client, paciente_id: str, dados_pessoais: schemas.PacienteUpdateDadosPessoais) -> Optional[Dict]:
    """Atualiza dados pessoais de um paciente."""
    try:
        user_ref = db.collection('usuarios').document(paciente_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            logger.warning(f"Paciente {paciente_id} não encontrado")
            return None
        
        # Preparar dados para atualização
        update_dict = {}
        
        if dados_pessoais.data_nascimento is not None:
            update_dict['data_nascimento'] = dados_pessoais.data_nascimento
        
        if dados_pessoais.sexo is not None:
            update_dict['sexo'] = dados_pessoais.sexo
        
        if dados_pessoais.estado_civil is not None:
            update_dict['estado_civil'] = dados_pessoais.estado_civil
        
        if dados_pessoais.profissao is not None:
            update_dict['profissao'] = dados_pessoais.profissao
        
        if dados_pessoais.escolaridade is not None:
            update_dict['escolaridade'] = dados_pessoais.escolaridade
        
        if dados_pessoais.renda_familiar is not None:
            update_dict['renda_familiar'] = dados_pessoais.renda_familiar
        
        if dados_pessoais.pessoas_na_casa is not None:
            update_dict['pessoas_na_casa'] = dados_pessoais.pessoas_na_casa
        
        if dados_pessoais.tem_plano_saude is not None:
            update_dict['tem_plano_saude'] = dados_pessoais.tem_plano_saude
        
        if dados_pessoais.plano_saude is not None:
            update_dict['plano_saude'] = dados_pessoais.plano_saude
        
        if dados_pessoais.contato_emergencia is not None:
            update_dict['contato_emergencia'] = dados_pessoais.contato_emergencia.model_dump()
        
        # Adicionar timestamp
        update_dict['updated_at'] = firestore.SERVER_TIMESTAMP
        
        # Atualizar
        user_ref.update(update_dict)
        
        # Retornar dados atualizados
        updated_doc = user_ref.get()
        updated_data = updated_doc.to_dict()
        updated_data['id'] = updated_doc.id
        
        # Descriptografar dados sensíveis
        updated_data = decrypt_user_sensitive_fields(updated_data, USER_SENSITIVE_FIELDS)
        
        if 'endereco' in updated_data and updated_data['endereco']:
            updated_data['endereco'] = decrypt_endereco_fields(updated_data['endereco'])
        
        logger.info(f"Dados pessoais do paciente {paciente_id} atualizados com sucesso")
        return updated_data
        
    except Exception as e:
        logger.error(f"Erro ao atualizar dados pessoais do paciente {paciente_id}: {e}")
        return None


def atualizar_endereco_paciente(db: firestore.client, paciente_id: str, endereco_data: schemas.EnderecoUpdate) -> Optional[Dict]:
    """Atualiza o endereço de um paciente."""
    try:
        user_ref = db.collection('usuarios').document(paciente_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            logger.warning(f"Paciente {paciente_id} não encontrado")
            return None
        
        # Criptografar dados do endereço
        endereco_dict = endereco_data.model_dump(exclude_unset=True)
        endereco_criptografado = encrypt_endereco_fields(endereco_dict)
        
        # Atualizar
        user_ref.update({
            'endereco': endereco_criptografado,
            'updated_at': firestore.SERVER_TIMESTAMP
        })
        
        # Retornar dados atualizados
        updated_doc = user_ref.get()
        updated_data = updated_doc.to_dict()
        updated_data['id'] = updated_doc.id
        
        # Descriptografar dados sensíveis
        updated_data = decrypt_user_sensitive_fields(updated_data, USER_SENSITIVE_FIELDS)
        
        if 'endereco' in updated_data and updated_data['endereco']:
            updated_data['endereco'] = decrypt_endereco_fields(updated_data['endereco'])
        
        logger.info(f"Endereço do paciente {paciente_id} atualizado com sucesso")
        return updated_data
        
    except Exception as e:
        logger.error(f"Erro ao atualizar endereço do paciente {paciente_id}: {e}")
        return None


def atualizar_consentimento_lgpd(db: firestore.client, user_id: str, consent_data: schemas.ConsentimentoLGPDUpdate) -> Optional[Dict]:
    """Atualiza o consentimento LGPD de um usuário."""
    try:
        user_ref = db.collection('usuarios').document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            logger.warning(f"Usuário {user_id} não encontrado")
            return None
        
        # Preparar dados de consentimento
        consentimento_dict = consent_data.model_dump()
        consentimento_dict['data_consentimento'] = firestore.SERVER_TIMESTAMP
        
        # Atualizar
        user_ref.update({
            'consentimento_lgpd': consentimento_dict,
            'updated_at': firestore.SERVER_TIMESTAMP
        })
        
        # Retornar dados atualizados
        updated_doc = user_ref.get()
        updated_data = updated_doc.to_dict()
        updated_data['id'] = updated_doc.id
        
        # Descriptografar dados sensíveis
        updated_data = decrypt_user_sensitive_fields(updated_data, USER_SENSITIVE_FIELDS)
        
        if 'endereco' in updated_data and updated_data['endereco']:
            updated_data['endereco'] = decrypt_endereco_fields(updated_data['endereco'])
        
        logger.info(f"Consentimento LGPD do usuário {user_id} atualizado com sucesso")
        return updated_data
        
    except Exception as e:
        logger.error(f"Erro ao atualizar consentimento LGPD do usuário {user_id}: {e}")
        return None