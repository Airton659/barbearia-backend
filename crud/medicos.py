# crud/medicos.py
"""
CRUD para gestão de médicos e relatórios médicos
"""

import logging
from typing import Optional, List, Dict
from firebase_admin import firestore
import schemas
from crud.utils import decrypt_user_sensitive_fields, add_timestamps

logger = logging.getLogger(__name__)

# Campos sensíveis que precisam de criptografia
USER_SENSITIVE_FIELDS = ['nome', 'telefone']


def criar_medico(db: firestore.client, medico_data: schemas.MedicoBase) -> Dict:
    """Cria um novo médico."""
    try:
        # Preparar dados
        medico_dict = medico_data.model_dump()
        medico_dict = add_timestamps(medico_dict, is_update=False)
        
        # Salvar no Firestore
        doc_ref = db.collection('medicos').document()
        doc_ref.set(medico_dict)
        medico_dict['id'] = doc_ref.id
        
        logger.info(f"Médico criado para usuário {medico_data.usuario_uid}")
        return medico_dict
        
    except Exception as e:
        logger.error(f"Erro ao criar médico: {e}")
        raise


def listar_medicos_por_negocio(db: firestore.client, negocio_id: str) -> List[Dict]:
    """Lista todos os médicos de um negócio."""
    medicos = []
    try:
        query = db.collection('medicos').where('negocio_id', '==', negocio_id)
        
        for doc in query.stream():
            medico_data = doc.to_dict()
            medico_data['id'] = doc.id
            
            # Buscar dados do usuário
            usuario_uid = medico_data.get('usuario_uid')
            if usuario_uid:
                user_query = db.collection('usuarios').where('firebase_uid', '==', usuario_uid).limit(1)
                user_docs = list(user_query.stream())
                
                if user_docs:
                    user_data = user_docs[0].to_dict()
                    user_data = decrypt_user_sensitive_fields(user_data, USER_SENSITIVE_FIELDS)
                    
                    medico_data.update({
                        'nome': user_data.get('nome'),
                        'email': user_data.get('email'),
                        'telefone': user_data.get('telefone')
                    })
            
            medicos.append(medico_data)
        
        logger.info(f"Retornando {len(medicos)} médicos para o negócio {negocio_id}")
        return medicos
    except Exception as e:
        logger.error(f"Erro ao listar médicos do negócio {negocio_id}: {e}")
        return []


def criar_relatorio_medico(db: firestore.client, paciente_id: str, relatorio_data: schemas.RelatorioMedicoCreate, autor: schemas.UsuarioProfile) -> Dict:
    """Cria um novo relatório médico."""
    try:
        # Preparar dados do relatório
        relatorio_dict = {
            'paciente_id': paciente_id,
            'autor_id': autor.id,
            'autor_nome': autor.nome,
            'autor_email': autor.email,
            'negocio_id': relatorio_data.negocio_id,
            'tipo': relatorio_data.tipo,
            'titulo': relatorio_data.titulo,
            'conteudo': relatorio_data.conteudo,
            'status': 'pendente',
            'prioridade': relatorio_data.prioridade or 'media',
            'data_solicitacao': firestore.SERVER_TIMESTAMP,
            'created_at': firestore.SERVER_TIMESTAMP,
            'updated_at': firestore.SERVER_TIMESTAMP
        }
        
        # Adicionar campos específicos se fornecidos
        if relatorio_data.data_consulta:
            relatorio_dict['data_consulta'] = relatorio_data.data_consulta
        if relatorio_data.observacoes:
            relatorio_dict['observacoes'] = relatorio_data.observacoes
        
        # Salvar no Firestore
        doc_ref = db.collection('relatorios_medicos').document()
        doc_ref.set(relatorio_dict)
        relatorio_dict['id'] = doc_ref.id
        
        logger.info(f"Relatório médico criado para paciente {paciente_id} por {autor.nome}")
        return relatorio_dict
        
    except Exception as e:
        logger.error(f"Erro ao criar relatório médico: {e}")
        raise


def listar_relatorios_por_paciente(db: firestore.client, paciente_id: str) -> List[Dict]:
    """Lista todos os relatórios médicos de um paciente."""
    relatorios = []
    try:
        query = db.collection('relatorios_medicos') \
                 .where('paciente_id', '==', paciente_id) \
                 .order_by('created_at', direction=firestore.Query.DESCENDING)
        
        for doc in query.stream():
            relatorio_data = doc.to_dict()
            relatorio_data['id'] = doc.id
            relatorios.append(relatorio_data)
        
        logger.info(f"Retornando {len(relatorios)} relatórios para o paciente {paciente_id}")
        return relatorios
    except Exception as e:
        logger.error(f"Erro ao listar relatórios do paciente {paciente_id}: {e}")
        return []


def listar_relatorios_pendentes_medico(db: firestore.client, medico_id: str, negocio_id: str) -> List[Dict]:
    """Lista todos os relatórios pendentes para um médico."""
    relatorios = []
    try:
        query = db.collection('relatorios_medicos') \
                 .where('negocio_id', '==', negocio_id) \
                 .where('status', '==', 'pendente') \
                 .order_by('data_solicitacao', direction=firestore.Query.ASCENDING)
        
        for doc in query.stream():
            relatorio_data = doc.to_dict()
            relatorio_data['id'] = doc.id
            relatorios.append(relatorio_data)
        
        logger.info(f"Retornando {len(relatorios)} relatórios pendentes para o médico {medico_id}")
        return relatorios
    except Exception as e:
        logger.error(f"Erro ao listar relatórios pendentes para o médico {medico_id}: {e}")
        return []


def atualizar_relatorio_medico(db: firestore.client, relatorio_id: str, update_data: schemas.RelatorioMedicoUpdate, usuario_id: str) -> Optional[Dict]:
    """Atualiza um relatório médico."""
    try:
        relatorio_ref = db.collection('relatorios_medicos').document(relatorio_id)
        relatorio_doc = relatorio_ref.get()
        
        if not relatorio_doc.exists:
            logger.warning(f"Relatório {relatorio_id} não encontrado")
            return None
        
        # Preparar dados para atualização
        update_dict = update_data.model_dump(exclude_unset=True)
        update_dict['updated_at'] = firestore.SERVER_TIMESTAMP
        
        # Se está sendo finalizado, adicionar médico responsável
        if update_data.status == 'finalizado':
            update_dict['medico_responsavel_id'] = usuario_id
            update_dict['data_finalizacao'] = firestore.SERVER_TIMESTAMP
        
        # Atualizar
        relatorio_ref.update(update_dict)
        
        # Retornar dados atualizados
        updated_doc = relatorio_ref.get()
        updated_data = updated_doc.to_dict()
        updated_data['id'] = updated_doc.id
        
        logger.info(f"Relatório {relatorio_id} atualizado com sucesso")
        return updated_data
        
    except Exception as e:
        logger.error(f"Erro ao atualizar relatório {relatorio_id}: {e}")
        return None


def listar_historico_relatorios_medico(db: firestore.client, medico_id: str, negocio_id: str, status_filter: Optional[str] = None) -> List[Dict]:
    """Lista o histórico de relatórios de um médico."""
    relatorios = []
    try:
        query = db.collection('relatorios_medicos') \
                 .where('medico_responsavel_id', '==', medico_id) \
                 .where('negocio_id', '==', negocio_id)
        
        if status_filter:
            query = query.where('status', '==', status_filter)
        
        query = query.order_by('data_finalizacao', direction=firestore.Query.DESCENDING)
        
        for doc in query.stream():
            relatorio_data = doc.to_dict()
            relatorio_data['id'] = doc.id
            relatorios.append(relatorio_data)
        
        logger.info(f"Retornando {len(relatorios)} relatórios no histórico do médico {medico_id}")
        return relatorios
    except Exception as e:
        logger.error(f"Erro ao listar histórico do médico {medico_id}: {e}")
        return []