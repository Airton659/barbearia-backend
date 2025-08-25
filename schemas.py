# barbearia-backend/schemas.py (Versão Definitiva)

from pydantic import BaseModel, EmailStr, Field, ConfigDict
from datetime import datetime, time, date
from typing import Optional, List, Dict, Union

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
# SCHEMAS DE USUÁRIOS
# =================================================================================

class UsuarioBase(BaseModel):
    nome: str
    email: EmailStr
    firebase_uid: str
    telefone: Optional[str] = None
    endereco: Optional[Dict[str, str]] = Field(None, description="Dicionário com dados de endereço.")

class UsuarioProfile(UsuarioBase):
    id: str = Field(..., description="ID do documento do usuário no Firestore.")
    roles: dict[str, str] = Field({}, description="Dicionário de negocio_id para role (ex: {'negocio_A': 'admin'}).")
    fcm_tokens: List[str] = []
    profissional_id: Optional[str] = Field(None, description="ID do perfil profissional, se aplicável.")
    supervisor_id: Optional[str] = Field(None, description="ID do usuário supervisor.")
    enfermeiro_vinculado_id: Optional[str] = Field(None, description="ID do profissional (enfermeiro) vinculado.")
    tecnicos_vinculados_ids: Optional[List[str]] = Field(None, description="Lista de IDs dos técnicos vinculados.")

class UsuarioSync(BaseModel):
    nome: str
    email: EmailStr
    firebase_uid: str
    negocio_id: Optional[str] = Field(None, description="ID do negócio ao qual o usuário está se cadastrando.")
    codigo_convite: Optional[str] = Field(None, description="Código de convite para se tornar admin.")
    telefone: Optional[str] = None
    endereco: Optional[Dict[str, str]] = None

class FCMTokenUpdate(BaseModel):
    fcm_token: str

class RoleUpdateRequest(BaseModel):
    role: str = Field(..., description="O novo papel do usuário (ex: 'cliente', 'profissional', 'admin', 'tecnico').")

class PacienteCreateByAdmin(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6, description="Senha para o novo paciente.")
    nome: str
    telefone: Optional[str] = None
    endereco: Optional[Dict[str, str]] = Field(None, description="Dicionário com dados de endereço.")

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
    enfermeiro_id: str

class TecnicosVincularRequest(BaseModel):
    tecnicos_ids: List[str] = Field(..., description="Lista de IDs de usuários dos técnicos.")

class SupervisorVincularRequest(BaseModel):
    supervisor_id: str = Field(..., description="ID do usuário do supervisor.")
    
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
    url_anexo: Optional[str] = None
    consulta_id: Optional[str] = Field(None, description="ID da consulta vinculada.")

class ExameCreate(ExameBase):
    pass

class ExameResponse(ExameBase):
    id: str

class ExameUpdate(BaseModel):
    nome_exame: Optional[str] = None
    data_exame: Optional[datetime] = None
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
    exames: List[ExameResponse]
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

class SinaisVitaisConteudo(BaseModel):
    pressao_sistolica: Optional[int] = None
    pressao_diastolica: Optional[int] = None
    temperatura: Optional[float] = None
    batimentos_cardiacos: Optional[int] = None
    saturacao_oxigenio: Optional[float] = None

class MedicacaoConteudo(BaseModel):
    nome: str
    dose: str
    status: str
    observacoes: Optional[str] = None

class AnotacaoConteudo(BaseModel):
    # Usado para tipos como 'anotacao' e 'atividade'
    descricao: str


class AtividadeConteudo(BaseModel):
    # Estrutura específica para o tipo 'atividade'
    nome_atividade: str
    descricao: Optional[str] = None
    duracao_minutos: int
    observacoes: Optional[str] = None

class IntercorrenciaConteudo(BaseModel):
    # Estrutura específica para o tipo 'intercorrencia' conforme o log
    tipo: str  # e.g., 'grave'
    descricao: str
    comunicado_enfermeiro: bool

# Union atualizada para incluir os novos modelos de conteúdo.
# Pydantic tentará validar o payload contra os modelos nesta ordem.
RegistroDiarioConteudo = Union[
    IntercorrenciaConteudo,
    AtividadeConteudo,
    AnotacaoConteudo,
    MedicacaoConteudo,
    SinaisVitaisConteudo
]

class RegistroDiarioCreate(BaseModel):
    negocio_id: str
    paciente_id: str
    tipo: str = Field(..., description="O tipo do registro (ex: 'sinais_vitais', 'medicacao', 'anotacao', 'intercorrencia', 'atividade').")
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

# =================================================================================
# REBUILD DE REFERÊNCIAS (ForwardRef)
# =================================================================================

ProfissionalResponse.model_rebuild()
DiarioTecnicoResponse.model_rebuild()