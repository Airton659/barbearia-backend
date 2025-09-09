# back/barbearia-backend/crud/pacientes.py
"""
CRUD para gestão de pacientes
"""

import logging
from typing import Optional, List, Dict
from firebase_admin import firestore
import schemas
from crud.utils import (
    decrypt_user_sensitive_fields,
    encrypt_endereco_fields,
    decrypt_endereco_fields,
    add_timestamps
)
from crypto_utils import decrypt_data

logger = logging.getLogger(__name__)

# Campos sensíveis que precisam de criptografia
USER_SENSITIVE_FIELDS = ['nome', 'telefone']


def listar_pacientes_por_profissional_ou_tecnico(db: firestore.client, negocio_id: str, usuario_id: str, role: str) -> List[Dict]:
    """
    Lista todos os pacientes ATIVOS.
    - Se a role for 'admin', retorna TODOS os pacientes do negócio.
    - Se a role for 'profissional' ou 'tecnico', retorna apenas os pacientes vinculados.
    """
    pacientes = []
    try:
        query = db.collection('usuarios').where(f'roles.{negocio_id}', '==', 'cliente')

        # Filtra por vínculo, se não for admin
        if role == 'admin':
            # Se for admin, não aplica filtro de vínculo, pega todos os clientes do negócio.
            pass
        elif role == 'profissional':
            query = query.where('enfermeiro_id', '==', usuario_id)
        elif role == 'tecnico':
            query = query.where('tecnicos_ids', 'array_contains', usuario_id)
        else:
            # Se a role não for nenhuma das esperadas, retorna lista vazia.
            return []

        for doc in query.stream():
            paciente_data = doc.to_dict()
            status_no_negocio = paciente_data.get('status_por_negocio', {}).get(negocio_id, 'ativo')

            if status_no_negocio == 'ativo':
                paciente_data['id'] = doc.id
                
                # CORREÇÃO CRÍTICA: Garantir que o firebase_uid esteja presente na resposta
                paciente_data['firebase_uid'] = paciente_data.get('firebase_uid')

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
        
        # Preparar dados para atualização (apenas campos que não são None)
        update_dict = dados_pessoais.model_dump(exclude_unset=True)

        if not update_dict:
            # Se nada foi enviado, apenas retorna os dados atuais
            updated_data = user_doc.to_dict()
            updated_data['id'] = user_doc.id
            updated_data = decrypt_user_sensitive_fields(updated_data, USER_SENSITIVE_FIELDS)
            if 'endereco' in updated_data and updated_data['endereco']:
                updated_data['endereco'] = decrypt_endereco_fields(updated_data['endereco'])
            return updated_data
            
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


def get_ficha_completa_paciente(db: firestore.client, paciente_id: str) -> Dict:
    """Retorna a ficha clínica completa do paciente."""
    from .anamneses import listar_consultas, listar_medicacoes, listar_checklist, listar_orientacoes
    
    try:
        # Buscar todas as consultas do paciente
        consultas = listar_consultas(db, paciente_id)
        
        # Se não há consultas, retornar estrutura vazia
        if not consultas:
            return {
                "consultas": [],
                "medicacoes": [],
                "checklist": [],
                "orientacoes": []
            }
        
        # Usar a consulta mais recente como padrão
        consulta_mais_recente = max(consultas, key=lambda x: x.get('data_consulta', ''))
        consulta_id = consulta_mais_recente.get('id')
        
        # Buscar dados relacionados à consulta mais recente
        medicacoes = listar_medicacoes(db, paciente_id, consulta_id) if consulta_id else []
        checklist = listar_checklist(db, paciente_id, consulta_id) if consulta_id else []
        orientacoes = listar_orientacoes(db, paciente_id, consulta_id) if consulta_id else []
        
        return {
            "consultas": consultas,
            "medicacoes": medicacoes,
            "checklist": checklist,
            "orientacoes": orientacoes
        }
        
    except Exception as e:
        logger.error(f"Erro ao buscar ficha completa do paciente {paciente_id}: {e}")
        return {
            "consultas": [],
            "medicacoes": [],
            "checklist": [],
            "orientacoes": []
        }