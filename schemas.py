# barbearia-backend/schemas.py (Versão Definitiva)

from pydantic import BaseModel, EmailStr, Field, ConfigDict
from datetime import datetime, time, date
from typing import Optional, List, Dict, Union
from enum import Enum
# =================================================================================
# SCHEMAS CENTRAIS (ARQUITETURA MULTI-TENANT)
# =================================================================================

class NegocioBase(BaseModel):
    nome: str = Field(..., description="Nome do negócio.")
    tipo_negocio: str = Field(..., description="Tipo do negócio (ex: 'barbearia', 'clinica').")

class NegocioCreate(NegocioBase):
    pass

class NegocioResponse(NegocioBase):
    id: str = Field(..., description="ID único do negócio no Firestore.")
    owner_uid: str = Field(..., description="Firebase UID do dono do negócio.")
    codigo_convite: str = Field(..., description="Código de convite para o admin do negócio.")



# =================================================================================
# 1. NOVO SCHEMA: ENDEREÇO (MOVIDO PARA CIMA PARA CORRIGIR O NameError)
# =================================================================================

class Endereco(BaseModel):
    rua: str
    numero: str
    cidade: str
    estado: str
    cep: str

class EnderecoUpdate(Endereco):
    pass

# =================================================================================
# SCHEMAS DE USUÁRIOS
# =================================================================================


# Em UsuarioBase, remova 'endereco'
class UsuarioBase(BaseModel):
    nome: str
    email: EmailStr
    firebase_uid: str
    telefone: Optional[str] = None
    # endereco: ... # LINHA REMOVIDA

# Em UsuarioProfile, adicione 'status_por_negocio' e o novo modelo de Endereco
class UsuarioProfile(UsuarioBase):
    id: str = Field(..., description="ID do documento do usuário no Firestore.")
    roles: dict[str, str] = Field({}, description="Dicionário de negocio_id para role.")
    status_por_negocio: Dict[str, str] = Field({}, description="Status do usuário por negócio (ex: 'ativo', 'inativo').")
    fcm_tokens: List[str] = []
    profissional_id: Optional[str] = Field(None, description="ID do perfil profissional, se aplicável.")
    supervisor_id: Optional[str] = Field(None, description="ID do usuário supervisor.")
    enfermeiro_vinculado_id: Optional[str] = Field(None, description="ID do profissional (enfermeiro) vinculado.")
    tecnicos_vinculados_ids: Optional[List[str]] = Field(None, description="Lista de IDs dos técnicos vinculados.")
    endereco: Optional[Endereco] = None
    
    # --- NOVOS CAMPOS ADICIONADOS AQUI ---
    consentimento_lgpd: Optional[bool] = None
    data_consentimento_lgpd: Optional[datetime] = None
    tipo_consentimento: Optional[str] = None

# Em UsuarioSync, remova 'endereco'
class UsuarioSync(BaseModel):
    nome: str
    email: EmailStr
    firebase_uid: str
    negocio_id: Optional[str] = None
    codigo_convite: Optional[str] = None
    telefone: Optional[str] = None
    # endereco: ... # LINHA REMOVIDA

class FCMTokenUpdate(BaseModel):
    fcm_token: str

class RoleUpdateRequest(BaseModel):
    role: str = Field(..., description="O novo papel do usuário (ex: 'cliente', 'profissional', 'admin', 'tecnico', 'medico').")

# Em PacienteCreateByAdmin, use o novo modelo Endereco
class PacienteCreateByAdmin(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)
    nome: str
    telefone: Optional[str] = None
    endereco: Optional[Endereco] = None

class StatusUpdateRequest(BaseModel):
    status: str = Field(..., description="O novo status do paciente (ex: 'ativo', 'arquivado').")

class PacienteProfile(UsuarioProfile):
    pass

# =================================================================================
# SCHEMAS DE PROFISSIONAIS
# =================================================================================

class ProfissionalBase(BaseModel):
    negocio_id: str
    usuario_uid: str
    nome: str
    especialidades: Optional[str] = None
    ativo: bool = True
    fotos: dict[str, str] = Field({}, description="URLs das fotos em diferentes tamanhos.")

class ProfissionalCreate(ProfissionalBase):
    pass

class ProfissionalResponse(ProfissionalBase):
    id: str = Field(..., description="ID do documento do profissional.")
    email: EmailStr = Field(..., description="E-mail do profissional.")
    servicos: List['ServicoResponse'] = []
    postagens: List['PostagemResponse'] = []
    avaliacoes: List['AvaliacaoResponse'] = []

class ProfissionalUpdate(BaseModel):
    especialidades: Optional[str] = None
    ativo: Optional[bool] = None
    fotos: Optional[dict[str, str]] = None

# =================================================================================
# SCHEMAS DE SERVIÇOS
# =================================================================================

class ServicoBase(BaseModel):
    negocio_id: str
    profissional_id: str
    nome: str
    descricao: Optional[str] = None
    preco: float
    duracao_minutos: int

class ServicoCreate(ServicoBase):
    pass

class ServicoResponse(ServicoBase):
    id: str = Field(..., description="ID do documento do serviço.")

class ServicoUpdate(BaseModel):
    nome: Optional[str] = None
    descricao: Optional[str] = None
    preco: Optional[float] = None
    duracao_minutos: Optional[int] = None

# =================================================================================
# SCHEMAS DE AGENDAMENTOS
# =================================================================================

class AgendamentoCreate(BaseModel):
    negocio_id: str
    profissional_id: str
    servico_id: str
    data_hora: datetime

class AgendamentoResponse(BaseModel):
    id: str
    negocio_id: str
    data_hora: datetime
    status: str
    cliente_id: str
    cliente_nome: str
    profissional_id: str
    profissional_nome: str
    profissional_foto_thumbnail: Optional[str] = None
    servico_id: str
    servico_nome: str
    servico_preco: float
    servico_duracao_minutos: int

# =================================================================================
# SCHEMAS DE INTERAÇÕES (FEED)
# =================================================================================

class PostagemCreate(BaseModel):
    negocio_id: str
    profissional_id: str
    titulo: str
    descricao: Optional[str] = None
    fotos: dict[str, str] = Field(..., description="URLs da postagem.")

class PostagemResponse(PostagemCreate):
    id: str
    data_postagem: datetime
    profissional_nome: str
    profissional_foto_thumbnail: Optional[str] = None
    total_curtidas: int = 0
    total_comentarios: int = 0
    curtido_pelo_usuario: bool = Field(False, description="Indica se o usuário autenticado curtiu.")

class ComentarioCreate(BaseModel):
    negocio_id: str
    postagem_id: str
    texto: str

class ComentarioResponse(ComentarioCreate):
    id: str
    data: datetime
    cliente_id: str
    cliente_nome: str

class AvaliacaoCreate(BaseModel):
    negocio_id: str
    profissional_id: str
    nota: int = Field(..., ge=1, le=5)
    comentario: Optional[str] = None

class AvaliacaoResponse(AvaliacaoCreate):
    id: str
    data: datetime
    cliente_id: str
    cliente_nome: str

# =================================================================================
# SCHEMAS DE GESTÃO CLÍNICA
# =================================================================================

class MedicoBase(BaseModel):
    negocio_id: str
    nome: str
    especialidade: str
    crm: Optional[str] = None

class MedicoResponse(MedicoBase):
    id: str

class MedicoUpdate(BaseModel):
    nome: Optional[str] = None
    especialidade: Optional[str] = None
    crm: Optional[str] = None

class VinculoCreate(BaseModel):
    paciente_id: str
    enfermeiro_id: Optional[str] = None # Tornou-se opcional

class TecnicosVincularRequest(BaseModel):
    tecnicos_ids: List[str] = Field(..., description="Lista de IDs de usuários dos técnicos.")

class SupervisorVincularRequest(BaseModel):
    supervisor_id: Optional[str] = Field(None, description="ID do usuário supervisor. Envie null para desvincular.")


# =================================================================================
# SCHEMAS DA FICHA DO PACIENTE
# =================================================================================

class ConsultaBase(BaseModel):
    negocio_id: str
    paciente_id: str
    data_consulta: datetime
    resumo: str
    medico_id: Optional[str] = None

class ConsultaCreate(ConsultaBase):
    pass

class ConsultaResponse(ConsultaBase):
    id: str

class ConsultaUpdate(BaseModel):
    data_consulta: Optional[datetime] = None
    resumo: Optional[str] = None
    medico_id: Optional[str] = None

class ExameBase(BaseModel):
    negocio_id: str
    paciente_id: str
    nome_exame: str
    data_exame: datetime
    horario_exame: Optional[str] = Field(None, description="Horário do exame (ex: '14:30').")
    descricao: Optional[str] = Field(None, description="Instruções ou observações sobre o exame.")
    url_anexo: Optional[str] = None
    
    # --- NOVOS CAMPOS DE AUDITORIA ADICIONADOS AQUI ---
    criado_por: Optional[str] = Field(None, description="Firebase UID do usuário que criou o exame.")
    data_criacao: Optional[datetime] = None
    data_atualizacao: Optional[datetime] = None


class ExameCreate(BaseModel):
    # Schema para criação, não inclui mais negocio_id e paciente_id no corpo
    nome_exame: str
    data_exame: datetime
    horario_exame: Optional[str] = None
    descricao: Optional[str] = None
    url_anexo: Optional[str] = None

class ExameResponse(ExameBase):
    id: str

class ExameUpdate(BaseModel):
    nome_exame: Optional[str] = None
    data_exame: Optional[datetime] = None # Também corrigido aqui
    horario_exame: Optional[str] = None
    descricao: Optional[str] = None
    url_anexo: Optional[str] = None

class MedicacaoBase(BaseModel):
    negocio_id: str
    paciente_id: str
    nome_medicamento: str
    dosagem: str
    instrucoes: str
    consulta_id: Optional[str] = Field(None, description="ID da consulta vinculada.")

class MedicacaoCreate(MedicacaoBase):
    data_criacao: datetime = Field(default_factory=datetime.utcnow)

class MedicacaoResponse(MedicacaoBase):
    id: str
    data_criacao: datetime

class MedicacaoUpdate(BaseModel):
    nome_medicamento: Optional[str] = None
    dosagem: Optional[str] = None
    instrucoes: Optional[str] = None

class ChecklistItemBase(BaseModel):
    negocio_id: str
    paciente_id: str
    descricao_item: str
    concluido: bool = False
    consulta_id: Optional[str] = Field(None, description="ID da consulta vinculada.")

class ChecklistItemCreate(ChecklistItemBase):
    data_criacao: datetime = Field(default_factory=datetime.utcnow)

class ChecklistItemResponse(ChecklistItemBase):
    id: str
    data_criacao: datetime

class ChecklistItemUpdate(BaseModel):
    descricao_item: Optional[str] = None
    concluido: Optional[bool] = None

class OrientacaoBase(BaseModel):
    negocio_id: str
    paciente_id: str
    titulo: str
    conteudo: str
    consulta_id: Optional[str] = Field(None, description="ID da consulta vinculada.")

class OrientacaoCreate(OrientacaoBase):
    data_criacao: datetime = Field(default_factory=datetime.utcnow)

class OrientacaoResponse(OrientacaoBase):
    id: str
    data_criacao: datetime

class OrientacaoUpdate(BaseModel):
    titulo: Optional[str] = None
    conteudo: Optional[str] = None

class FichaCompletaResponse(BaseModel):
    consultas: List[ConsultaResponse]
    medicacoes: List[MedicacaoResponse]
    checklist: List[ChecklistItemResponse]
    orientacoes: List[OrientacaoResponse]
    
# =================================================================================
# SCHEMAS DE DISPONIBILIDADE
# =================================================================================

class HorarioTrabalho(BaseModel):
    dia_semana: int
    hora_inicio: time
    hora_fim: time

class Bloqueio(BaseModel):
    inicio: datetime
    fim: datetime
    motivo: Optional[str] = None
    
# =================================================================================
# SCHEMAS DE NOTIFICAÇÕES
# =================================================================================

class NotificacaoResponse(BaseModel):
    id: str
    title: str
    body: str
    lida: bool
    data_criacao: datetime
    tipo: Optional[str] = None
    relacionado: Optional[Dict[str, str]] = None

class NotificacaoContagemResponse(BaseModel):
    count: int

class MarcarLidaRequest(BaseModel):
    notificacao_id: str

class NotificacaoAgendadaCreate(BaseModel):
    paciente_id: str
    negocio_id: str
    titulo: str
    mensagem: str
    data_agendamento: datetime

class NotificacaoAgendadaResponse(NotificacaoAgendadaCreate):
    id: str
    status: str = "agendada"
    criado_em: datetime
    criado_por_uid: str

# =================================================================================
# SCHEMAS DO FLUXO DO TÉCNICO
# =================================================================================

class TecnicoProfileReduzido(BaseModel):
    id: str
    nome: str
    email: EmailStr

class DiarioTecnicoBase(BaseModel):
    negocio_id: str
    paciente_id: str
    anotacao_geral: str
    medicamentos: Optional[str] = None
    atividades: Optional[str] = None
    intercorrencias: Optional[str] = None

class DiarioTecnicoCreate(DiarioTecnicoBase):
    pass

class DiarioTecnicoResponse(DiarioTecnicoBase):
    id: str
    data_ocorrencia: datetime
    tecnico: 'TecnicoProfileReduzido'

class DiarioTecnicoUpdate(BaseModel):
    anotacao_geral: Optional[str] = None
    medicamentos: Optional[str] = None
    atividades: Optional[str] = None
    intercorrencias: Optional[str] = None

# --- Início da Correção de Registros Diários ---

# class SinaisVitaisConteudo(BaseModel):
#     pressao_sistolica: Optional[int] = None
#     pressao_diastolica: Optional[int] = None
#     temperatura: Optional[float] = None
#     batimentos_cardiacos: Optional[int] = None
#     saturacao_oxigenio: Optional[float] = None

# class MedicacaoConteudo(BaseModel):
#     nome: str
#     dose: str
#     status: str
#     observacoes: Optional[str] = None

class AnotacaoConteudo(BaseModel):
    # Usado para tipos como 'anotacao' e 'atividade'
    descricao: str


# class AtividadeConteudo(BaseModel):
#     # Estrutura específica para o tipo 'atividade'
#     nome_atividade: str
#     descricao: Optional[str] = None
#     duracao_minutos: int
#     observacoes: Optional[str] = None

# class IntercorrenciaConteudo(BaseModel):
#     # Estrutura específica para o tipo 'intercorrencia' conforme o log
#     tipo: str  # e.g., 'grave'
#     descricao: str
#     comunicado_enfermeiro: bool

# # Union atualizada para incluir os novos modelos de conteúdo.
# # Pydantic tentará validar o payload contra os modelos nesta ordem.
# RegistroDiarioConteudo = Union[
#     IntercorrenciaConteudo,
#     AtividadeConteudo,
#     AnotacaoConteudo,
#     MedicacaoConteudo,
#     SinaisVitaisConteudo
# ]

# class RegistroDiarioCreate(BaseModel):
#     negocio_id: str
#     paciente_id: str
#     tipo: str = Field(..., description="O tipo do registro (ex: 'sinais_vitais', 'medicacao', 'anotacao', 'intercorrencia', 'atividade').")
#     conteudo: RegistroDiarioConteudo
RegistroDiarioConteudo = AnotacaoConteudo

class RegistroDiarioCreate(BaseModel):
    negocio_id: str
    paciente_id: str
    tipo: str = Field(..., description="O tipo do registro (ex: 'sinais_vitais', 'medicacao', 'anotacao').")
    # Adiciona o timestamp enviado pelo app
    data_hora: datetime = Field(..., description="Timestamp exato do evento, enviado pelo app.")
    # Usa o novo modelo de conteúdo simplificado
    conteudo: RegistroDiarioConteudo

class RegistroDiarioResponse(BaseModel):
    id: str
    negocio_id: str
    paciente_id: str
    tecnico: 'TecnicoProfileReduzido'
    data_registro: datetime
    tipo: str
    conteudo: RegistroDiarioConteudo

# --- Fim da Correção de Registros Diários ---

class ConfirmacaoLeituraCreate(BaseModel):
    usuario_id: str
    plano_version_id: str
    ip_origem: Optional[str] = None

class ConfirmacaoLeituraResponse(ConfirmacaoLeituraCreate):
    id: str
    paciente_id: str
    data_confirmacao: datetime

class ChecklistItemDiarioResponse(BaseModel):
    id: str
    descricao: str
    concluido: bool

class ChecklistItemDiarioUpdate(BaseModel):
    concluido: bool

# =================================================================================
# SCHEMAS DA PESQUISA DE SATISFAÇÃO
# =================================================================================

class RespostaItem(BaseModel):
    pergunta_id: str
    pergunta_texto: str
    resposta: str

class PesquisaEnviadaCreate(BaseModel):
    negocio_id: str
    paciente_id: str
    modelo_pesquisa_id: str

class PesquisaEnviadaResponse(PesquisaEnviadaCreate):
    id: str
    data_envio: datetime
    data_resposta: Optional[datetime] = None
    status: str = Field("pendente", description="Status: 'pendente' ou 'respondida'.")
    respostas: List[RespostaItem] = []

class SubmeterPesquisaRequest(BaseModel):
    respostas: List[RespostaItem]
    
# =================================================================================
# SCHEMAS DO PLANO DE CUIDADO (ACK)
# =================================================================================

class PlanoAckCreate(BaseModel):
    paciente_id: int = Field(..., description="ID do paciente")
    tecnico_id: int = Field(..., description="ID do técnico que confirma a leitura")
    plano_version_id: str = Field(..., min_length=1, description="Identificador da versão publicada do plano")

class PlanoAckRead(BaseModel):
    id: int
    paciente_id: int
    tecnico_id: int
    plano_version_id: str
    ack_date: date
    ack_at: datetime

    model_config = ConfigDict(from_attributes=True)

class PlanoAckStatus(BaseModel):
    ackHoje: bool = Field(..., description="Se já houve confirmação hoje para a versão atual do plano")
    planoVersionId: Optional[str] = Field(None, description="Versão do plano considerada no status")

# Em schemas.py, SUBSTITUA as classes de Anamnese por este bloco inteiro:

# Em schemas.py, SUBSTITUA todas as classes de Anamnese por este bloco:

# =================================================================================
# SCHEMAS DA FICHA DE AVALIAÇÃO DE ENFERMAGEM (ANAMNESE) - VERSÃO FINAL, COMPLETA E CORRETA
# =================================================================================

class SinaisVitaisAnamnese(BaseModel):
    # OBRIGATÓRIOS (Conforme Seção 4)
    pa: str
    fc: str
    fr: str
    temp: str
    spo2: str

class AnamneseEnfermagemBase(BaseModel):
    # --- DADOS GERAIS OBRIGATÓRIOS ---
    nome_paciente: str
    data_avaliacao: datetime
    responsavel_id: str

    # --- SEÇÃO 1: Identificação do Paciente (OBRIGATÓRIO) ---
    idade: int
    sexo: str
    estado_civil: str
    profissao: str

    # --- SEÇÃO 3: Histórico de Enfermagem (OPCIONAL) ---
    queixa_principal: Optional[str] = None
    historia_doenca_atual: Optional[str] = None
    antecedentes_doencas: List[str] = Field(default_factory=list)
    antecedentes_outros: Optional[str] = None
    cirurgias_anteriores: Optional[str] = None
    alergias: Optional[str] = None
    medicamentos_continuos: Optional[str] = None
    habitos: List[str] = Field(default_factory=list)
    habitos_outros: Optional[str] = None
    historia_familiar: Optional[str] = None

    # --- SEÇÃO 4: Avaliação do Estado Atual (OBRIGATÓRIO) ---
    sinais_vitais: SinaisVitaisAnamnese
    nivel_consciencia: str
    estado_nutricional: str
    pele_mucosas: str
    sistema_respiratorio: str
    sistema_cardiovascular: str
    abdome: str
    eliminacoes_fisiologicas: str
    drenos_sondas_cateteres: str

    # --- SEÇÃO 5: Aspectos Psicossociais (OPCIONAL) ---
    apoio_familiar_social: Optional[str] = None
    necessidades_emocionais_espirituais: Optional[str] = None

class AnamneseEnfermagemCreate(AnamneseEnfermagemBase):
    pass

class AnamneseEnfermagemUpdate(BaseModel):
    # CÓDIGO COMPLETO, SEM RESUMO
    nome_paciente: Optional[str] = None
    data_avaliacao: Optional[datetime] = None
    responsavel_id: Optional[str] = None
    idade: Optional[int] = None
    sexo: Optional[str] = None
    estado_civil: Optional[str] = None
    profissao: Optional[str] = None
    queixa_principal: Optional[str] = None
    historia_doenca_atual: Optional[str] = None
    antecedentes_doencas: Optional[List[str]] = None
    antecedentes_outros: Optional[str] = None
    cirurgias_anteriores: Optional[str] = None
    alergias: Optional[str] = None
    medicamentos_continuos: Optional[str] = None
    habitos: Optional[List[str]] = None
    habitos_outros: Optional[str] = None
    historia_familiar: Optional[str] = None
    sinais_vitais: Optional[SinaisVitaisAnamnese] = None
    nivel_consciencia: Optional[str] = None
    estado_nutricional: Optional[str] = None
    pele_mucosas: Optional[str] = None
    sistema_respiratorio: Optional[str] = None
    sistema_cardiovascular: Optional[str] = None
    abdome: Optional[str] = None
    eliminacoes_fisiologicas: Optional[str] = None
    drenos_sondas_cateteres: Optional[str] = None
    apoio_familiar_social: Optional[str] = None
    necessidades_emocionais_espirituais: Optional[str] = None

class AnamneseEnfermagemResponse(AnamneseEnfermagemBase):
    id: str
    paciente_id: str
    created_at: datetime
    updated_at: Optional[datetime] = None


# =================================================================================
# SCHEMAS DE SUPORTE PSICOLÓGICO
# =================================================================================

class SuportePsicologicoBase(BaseModel):
    titulo: str = Field(..., min_length=3, max_length=100)
    conteudo: str = Field(..., min_length=5, max_length=1000)

class SuportePsicologicoCreate(SuportePsicologicoBase):
    pass

class SuportePsicologicoUpdate(BaseModel):
    titulo: Optional[str] = Field(None, min_length=3, max_length=100)
    conteudo: Optional[str] = Field(None, min_length=5, max_length=1000)

class SuportePsicologicoResponse(SuportePsicologicoBase):
    id: str
    paciente_id: str
    negocio_id: str
    tipo: str = Field(..., description="'link' ou 'texto'")
    criado_por: str = Field(..., description="ID do usuário que criou o recurso.")
    data_criacao: datetime
    data_atualizacao: Optional[datetime] = None

# =================================================================================
# NOVO: SCHEMAS DE CONSENTIMENTO LGPD
# =================================================================================

class TipoConsentimentoEnum(str, Enum):
    digital = "digital"
    fisico = "fisico"

class ConsentimentoLGPDUpdate(BaseModel):
    consentimento_lgpd: bool
    data_consentimento_lgpd: datetime
    tipo_consentimento: TipoConsentimentoEnum


# =================================================================================
# SCHEMAS DE RELATÓRIO MÉDICO
# =================================================================================

class RelatorioMedicoBase(BaseModel):
    paciente_id: str
    negocio_id: str
    criado_por_id: str
    medico_id: str
    consulta_id: str
    status: str = "pendente"
    fotos: List[str] = Field(default_factory=list)
    motivo_recusa: Optional[str] = None
    data_criacao: datetime
    data_revisao: Optional[datetime] = None

class RelatorioMedicoCreate(BaseModel):
    medico_id: str = Field(..., description="ID do usuário médico que avaliará o relatório.")
    negocio_id: str = Field(..., description="ID do negócio ao qual o relatório pertence.")

class RelatorioMedicoResponse(RelatorioMedicoBase):
    id: str

class RecusarRelatorioRequest(BaseModel):
    motivo: str = Field(..., description="Justificativa da recusa.")

class RelatorioCompletoResponse(BaseModel):
    relatorio: RelatorioMedicoResponse
    paciente: UsuarioProfile
    planoCuidado: FichaCompletaResponse
    registrosDiarios: List[RegistroDiarioResponse]

ProfissionalResponse.model_rebuild()
DiarioTecnicoResponse.model_rebuild()