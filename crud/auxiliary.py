# crud/auxiliary.py
"""
CRUD para funções auxiliares e utilitárias diversas
"""

import logging
from typing import Optional, List, Dict
from firebase_admin import firestore
from datetime import date, time, datetime, timedelta
import schemas
from crud.utils import add_timestamps

logger = logging.getLogger(__name__)


def calcular_horarios_disponiveis(db: firestore.client, profissional_id: str, dia: date, duracao_servico_min: int = 60) -> List[time]:
    """Calcula os horários disponíveis de um profissional para um dia específico."""
    try:
        horarios_disponiveis = []
        
        # Buscar horários de trabalho do profissional para o dia da semana
        dia_semana = dia.weekday()  # 0 = segunda, 6 = domingo
        
        horarios_query = db.collection('horarios_trabalho') \
                          .where('profissional_id', '==', profissional_id) \
                          .where('dia_semana', '==', dia_semana)
        
        horarios_trabalho = list(horarios_query.stream())
        
        if not horarios_trabalho:
            logger.info(f"Nenhum horário de trabalho encontrado para profissional {profissional_id} no dia {dia}")
            return []
        
        for horario_doc in horarios_trabalho:
            horario_data = horario_doc.to_dict()
            hora_inicio = datetime.fromisoformat(horario_data['hora_inicio']).time()
            hora_fim = datetime.fromisoformat(horario_data['hora_fim']).time()
            
            # Gerar slots de tempo baseados na duração do serviço
            current_time = datetime.combine(dia, hora_inicio)
            end_time = datetime.combine(dia, hora_fim)
            
            while current_time + timedelta(minutes=duracao_servico_min) <= end_time:
                slot_time = current_time.time()
                
                # Verificar se o horário não está ocupado
                if not _horario_ocupado(db, profissional_id, dia, slot_time, duracao_servico_min):
                    horarios_disponiveis.append(slot_time)
                
                current_time += timedelta(minutes=duracao_servico_min)
        
        horarios_disponiveis.sort()
        logger.info(f"Encontrados {len(horarios_disponiveis)} horários disponíveis para {dia}")
        return horarios_disponiveis
        
    except Exception as e:
        logger.error(f"Erro ao calcular horários disponíveis: {e}")
        return []


def _horario_ocupado(db: firestore.client, profissional_id: str, dia: date, horario: time, duracao_min: int) -> bool:
    """Verifica se um horário específico está ocupado."""
    try:
        inicio_slot = datetime.combine(dia, horario)
        fim_slot = inicio_slot + timedelta(minutes=duracao_min)
        
        # Buscar agendamentos que conflitam com o horário
        agendamentos_query = db.collection('agendamentos') \
                             .where('profissional_id', '==', profissional_id) \
                             .where('status', 'in', ['agendado', 'confirmado'])
        
        for doc in agendamentos_query.stream():
            agendamento = doc.to_dict()
            data_hora_agendamento = agendamento.get('data_hora')
            
            if isinstance(data_hora_agendamento, str):
                data_hora_agendamento = datetime.fromisoformat(data_hora_agendamento)
            elif hasattr(data_hora_agendamento, 'replace'):
                data_hora_agendamento = data_hora_agendamento.replace(tzinfo=None)
            
            if data_hora_agendamento.date() == dia:
                fim_agendamento = data_hora_agendamento + timedelta(minutes=agendamento.get('duracao_minutos', 60))
                
                # Verificar sobreposição
                if (inicio_slot < fim_agendamento and fim_slot > data_hora_agendamento):
                    return True
        
        return False
        
    except Exception as e:
        logger.error(f"Erro ao verificar se horário está ocupado: {e}")
        return True


def criar_avaliacao(db: firestore.client, avaliacao_data: schemas.AvaliacaoCreate, usuario: schemas.UsuarioProfile) -> Dict:
    """Cria uma nova avaliação de serviço."""
    try:
        avaliacao_dict = {
            'agendamento_id': avaliacao_data.agendamento_id,
            'profissional_id': avaliacao_data.profissional_id,
            'cliente_id': usuario.id,
            'cliente_nome': usuario.nome,
            'nota': avaliacao_data.nota,
            'comentario': avaliacao_data.comentario or '',
            'aspectos_avaliados': avaliacao_data.aspectos_avaliados or {},
            'recomendaria': avaliacao_data.recomendaria
        }
        
        avaliacao_dict = add_timestamps(avaliacao_dict, is_update=False)
        
        doc_ref = db.collection('avaliacoes').document()
        doc_ref.set(avaliacao_dict)
        avaliacao_dict['id'] = doc_ref.id
        
        logger.info(f"Avaliação criada para agendamento {avaliacao_data.agendamento_id}")
        return avaliacao_dict
        
    except Exception as e:
        logger.error(f"Erro ao criar avaliação: {e}")
        raise


def listar_avaliacoes_por_profissional(db: firestore.client, profissional_id: str) -> List[Dict]:
    """Lista todas as avaliações de um profissional."""
    avaliacoes = []
    try:
        query = db.collection('avaliacoes') \
                 .where('profissional_id', '==', profissional_id) \
                 .order_by('created_at', direction=firestore.Query.DESCENDING)
        
        for doc in query.stream():
            avaliacao_data = doc.to_dict()
            avaliacao_data['id'] = doc.id
            avaliacoes.append(avaliacao_data)
        
        logger.info(f"Retornando {len(avaliacoes)} avaliações do profissional {profissional_id}")
        return avaliacoes
        
    except Exception as e:
        logger.error(f"Erro ao listar avaliações: {e}")
        return []


def vincular_paciente_enfermeiro(db: firestore.client, negocio_id: str, paciente_id: str, enfermeiro_id: Optional[str], autor_uid: str) -> Optional[Dict]:
    """Vincula um paciente a um enfermeiro."""
    try:
        paciente_ref = db.collection('usuarios').document(paciente_id)
        paciente_doc = paciente_ref.get()
        
        if not paciente_doc.exists:
            return None
        
        update_data = {
            f'vinculos.{negocio_id}.enfermeiro_id': enfermeiro_id,
            'updated_at': firestore.SERVER_TIMESTAMP
        }
        
        paciente_ref.update(update_data)
        
        logger.info(f"Paciente {paciente_id} vinculado ao enfermeiro {enfermeiro_id}")
        
        updated_doc = paciente_ref.get()
        updated_data = updated_doc.to_dict()
        updated_data['id'] = updated_doc.id
        
        return updated_data
        
    except Exception as e:
        logger.error(f"Erro ao vincular paciente ao enfermeiro: {e}")
        return None


def desvincular_paciente_enfermeiro(db: firestore.client, negocio_id: str, paciente_id: str, autor_uid: str) -> Optional[Dict]:
    """Desvincula um paciente de um enfermeiro."""
    try:
        paciente_ref = db.collection('usuarios').document(paciente_id)
        paciente_doc = paciente_ref.get()
        
        if not paciente_doc.exists:
            return None
        
        update_data = {
            f'vinculos.{negocio_id}.enfermeiro_id': None,
            'updated_at': firestore.SERVER_TIMESTAMP
        }
        
        paciente_ref.update(update_data)
        
        logger.info(f"Paciente {paciente_id} desvinculado do enfermeiro")
        
        updated_doc = paciente_ref.get()
        updated_data = updated_doc.to_dict()
        updated_data['id'] = updated_doc.id
        
        return updated_data
        
    except Exception as e:
        logger.error(f"Erro ao desvincular paciente do enfermeiro: {e}")
        return None


def vincular_paciente_medico(db: firestore.client, negocio_id: str, paciente_id: str, medico_id: Optional[str], autor_uid: str) -> Optional[Dict]:
    """Vincula um paciente a um médico."""
    try:
        paciente_ref = db.collection('usuarios').document(paciente_id)
        paciente_doc = paciente_ref.get()
        
        if not paciente_doc.exists:
            return None
        
        update_data = {
            f'vinculos.{negocio_id}.medico_id': medico_id,
            'updated_at': firestore.SERVER_TIMESTAMP
        }
        
        paciente_ref.update(update_data)
        
        logger.info(f"Paciente {paciente_id} vinculado ao médico {medico_id}")
        
        updated_doc = paciente_ref.get()
        updated_data = updated_doc.to_dict()
        updated_data['id'] = updated_doc.id
        
        return updated_data
        
    except Exception as e:
        logger.error(f"Erro ao vincular paciente ao médico: {e}")
        return None


def vincular_tecnicos_paciente(db: firestore.client, paciente_id: str, tecnicos_ids: List[str], autor_uid: str) -> Optional[Dict]:
    """Vincula múltiplos técnicos a um paciente."""
    try:
        paciente_ref = db.collection('usuarios').document(paciente_id)
        paciente_doc = paciente_ref.get()
        
        if not paciente_doc.exists:
            return None
        
        update_data = {
            'tecnicos_vinculados': tecnicos_ids,
            'updated_at': firestore.SERVER_TIMESTAMP
        }
        
        paciente_ref.update(update_data)
        
        logger.info(f"Paciente {paciente_id} vinculado aos técnicos {tecnicos_ids}")
        
        updated_doc = paciente_ref.get()
        updated_data = updated_doc.to_dict()
        updated_data['id'] = updated_doc.id
        
        return updated_data
        
    except Exception as e:
        logger.error(f"Erro ao vincular técnicos ao paciente: {e}")
        return None


def vincular_supervisor_tecnico(db: firestore.client, tecnico_id: str, supervisor_id: Optional[str], autor_uid: str) -> Optional[Dict]:
    """Vincula um técnico a um supervisor."""
    try:
        tecnico_ref = db.collection('usuarios').document(tecnico_id)
        tecnico_doc = tecnico_ref.get()
        
        if not tecnico_doc.exists:
            return None
        
        update_data = {
            'supervisor_id': supervisor_id,
            'updated_at': firestore.SERVER_TIMESTAMP
        }
        
        tecnico_ref.update(update_data)
        
        logger.info(f"Técnico {tecnico_id} vinculado ao supervisor {supervisor_id}")
        
        updated_doc = tecnico_ref.get()
        updated_data = updated_doc.to_dict()
        updated_data['id'] = updated_doc.id
        
        return updated_data
        
    except Exception as e:
        logger.error(f"Erro ao vincular supervisor ao técnico: {e}")
        return None


def enviar_pesquisa_satisfacao(db: firestore.client, envio_data: schemas.PesquisaEnviadaCreate) -> Dict:
    """Envia uma pesquisa de satisfação para um paciente."""
    try:
        envio_dict = {
            'modelo_pesquisa_id': envio_data.modelo_pesquisa_id,
            'paciente_id': envio_data.paciente_id,
            'negocio_id': envio_data.negocio_id,
            'data_envio': firestore.SERVER_TIMESTAMP,
            'data_limite_resposta': envio_data.data_limite_resposta,
            'status': 'enviada',
            'respondida': False
        }
        
        envio_dict = add_timestamps(envio_dict, is_update=False)
        
        doc_ref = db.collection('pesquisas_enviadas').document()
        doc_ref.set(envio_dict)
        envio_dict['id'] = doc_ref.id
        
        logger.info(f"Pesquisa enviada para paciente {envio_data.paciente_id}")
        return envio_dict
        
    except Exception as e:
        logger.error(f"Erro ao enviar pesquisa: {e}")
        raise


def submeter_respostas_pesquisa(db: firestore.client, pesquisa_enviada_id: str, respostas_data: schemas.SubmeterPesquisaRequest, paciente_id: str) -> Optional[Dict]:
    """Submete as respostas de uma pesquisa de satisfação."""
    try:
        pesquisa_ref = db.collection('pesquisas_enviadas').document(pesquisa_enviada_id)
        pesquisa_doc = pesquisa_ref.get()
        
        if not pesquisa_doc.exists:
            return None
        
        pesquisa_data = pesquisa_doc.to_dict()
        
        # Verificar se a pesquisa pertence ao paciente
        if pesquisa_data.get('paciente_id') != paciente_id:
            return None
        
        # Atualizar com as respostas
        update_data = {
            'respostas': respostas_data.respostas,
            'data_resposta': firestore.SERVER_TIMESTAMP,
            'respondida': True,
            'status': 'respondida',
            'updated_at': firestore.SERVER_TIMESTAMP
        }
        
        pesquisa_ref.update(update_data)
        
        logger.info(f"Respostas submetidas para pesquisa {pesquisa_enviada_id}")
        
        updated_doc = pesquisa_ref.get()
        updated_data = updated_doc.to_dict()
        updated_data['id'] = updated_doc.id
        
        return updated_data
        
    except Exception as e:
        logger.error(f"Erro ao submeter respostas da pesquisa: {e}")
        return None


def listar_pesquisas_por_paciente(db: firestore.client, negocio_id: str, paciente_id: str) -> List[Dict]:
    """Lista todas as pesquisas enviadas para um paciente."""
    pesquisas = []
    try:
        query = db.collection('pesquisas_enviadas') \
                 .where('paciente_id', '==', paciente_id) \
                 .where('negocio_id', '==', negocio_id) \
                 .order_by('data_envio', direction=firestore.Query.DESCENDING)
        
        for doc in query.stream():
            pesquisa_data = doc.to_dict()
            pesquisa_data['id'] = doc.id
            pesquisas.append(pesquisa_data)
        
        logger.info(f"Retornando {len(pesquisas)} pesquisas para paciente {paciente_id}")
        return pesquisas
        
    except Exception as e:
        logger.error(f"Erro ao listar pesquisas do paciente: {e}")
        return []


def listar_resultados_pesquisas(db: firestore.client, negocio_id: str, modelo_pesquisa_id: Optional[str] = None) -> List[Dict]:
    """Lista os resultados das pesquisas de um negócio."""
    resultados = []
    try:
        query = db.collection('pesquisas_enviadas') \
                 .where('negocio_id', '==', negocio_id) \
                 .where('respondida', '==', True)
        
        if modelo_pesquisa_id:
            query = query.where('modelo_pesquisa_id', '==', modelo_pesquisa_id)
        
        query = query.order_by('data_resposta', direction=firestore.Query.DESCENDING)
        
        for doc in query.stream():
            resultado_data = doc.to_dict()
            resultado_data['id'] = doc.id
            resultados.append(resultado_data)
        
        logger.info(f"Retornando {len(resultados)} resultados de pesquisas")
        return resultados
        
    except Exception as e:
        logger.error(f"Erro ao listar resultados das pesquisas: {e}")
        return []