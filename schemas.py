# barbearia-backend/schemas.py (Versão para Firestore Multi-Tenant)

from pydantic import BaseModel, EmailStr, Field
from datetime import datetime, time
from typing import Optional, List, Dict, Union

# =================================================================================
# NOVOS SCHEMAS CENTRAIS (A BASE DA ARQUITETURA MULTI-TENANT)
# =================================================================================

class NegocioBase(BaseModel):
    nome: str = Field(..., description="Nome do negócio (ex: Barbearia do Zé, Confeitaria da Maria).")
    tipo_negocio: str = Field(..., description="Tipo do negócio (ex: 'barbearia', 'confeitaria', 'salao_de_beleza').")
    # Outros campos relevantes para um negócio: endereço, telefone, etc.

class NegocioCreate(NegocioBase):
    pass

class NegocioResponse(NegocioBase):
    id: str = Field(..., description="ID único do negócio no Firestore.")
    owner_uid: str = Field(..., description="Firebase UID do usuário dono do negócio.")
    codigo_convite: str = Field(..., description="Código de convite para o admin do negócio se registrar.")

# =================================================================================
# SCHEMAS DE USUÁRIOS (Clientes e Administradores)
# =================================================================================

class UsuarioBase(BaseModel):
    nome: str
    email: EmailStr
    firebase_uid: str
    # --- ALTERAÇÃO AQUI: Adicionando campos opcionais para o app clínico ---
    telefone: Optional[str] = None
    endereco: Optional[Dict[str, str]] = Field(None, description="Dicionário com dados de endereço. Ex: {'rua': 'Av. Exemplo', 'numero': '123', 'cidade': 'São Paulo'}")
    # --- FIM DA ALTERAÇÃO ---


class UsuarioCreate(UsuarioBase):
    # No Firestore, o usuário é criado via Firebase Auth, então o backend só sincroniza.
    pass

class UsuarioProfile(UsuarioBase):
    id: str = Field(..., description="ID do documento do usuário no Firestore.")
    # Um usuário pode ser membro de múltiplos negócios (ex: admin de um, cliente de outro)
    roles: dict[str, str] = Field({}, description="Dicionário de negocio_id para role (ex: {'negocio_A': 'admin', 'negocio_B': 'cliente'}).")
    fcm_tokens: List[str] = []
    profissional_id: Optional[str] = Field(None, description="ID do perfil profissional, se o usuário for um profissional ou admin.")
    # Adicionando o campo supervisor_id para a nova funcionalidade
    supervisor_id: Optional[str] = Field(None, description="ID do usuário (documento) do enfermeiro supervisor.")


# Schema usado pelo endpoint de sync, agora com o negocio_id opcional
class UsuarioSync(BaseModel):
    nome: str
    email: EmailStr
    firebase_uid: str
    negocio_id: Optional[str] = Field(None, description="ID do negócio ao qual o usuário (cliente) está se cadastrando.")
    codigo_convite: Optional[str] = Field(None, description="Código de convite para se tornar admin de um negócio.")
    telefone: Optional[str] = None
    endereco: Optional[Dict[str, str]] = None

# Schema para registrar o token de notificação
class FCMTokenUpdate(BaseModel):
    fcm_token: str

# Perfis para o módulo clínico, herdando do perfil base para compatibilidade
class EnfermeiroProfile(UsuarioProfile):
    pass

class PacienteProfile(UsuarioProfile):
    pass

class RoleUpdateRequest(BaseModel):
    # --- ALTERAÇÃO AQUI: Adicionando 'tecnico' como um papel válido ---
    role: str = Field(..., description="O novo papel do usuário (ex: 'cliente', 'profissional', 'admin', 'tecnico').")
    # --- FIM DA ALTERAÇÃO ---

class PacienteCreateByAdmin(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6, description="Senha para o novo paciente. Deve ser forte.")
    nome: str
    telefone: Optional[str] = None
    endereco: Optional[Dict[str, str]] = Field(None, description="Dicionário com dados de endereço.")

class StatusUpdateRequest(BaseModel):
    status: str = Field(..., description="O novo status do paciente (ex: 'ativo', 'arquivado').")


# =================================================================================
# SCHEMAS DE PROFISSIONAIS (Antigos Barbeiros)
# =================================================================================

class ProfissionalBase(BaseModel):
    negocio_id: str
    usuario_uid: str # Firebase UID do usuário que é o profissional
    nome: str # Desnormalizado para leituras rápidas
    especialidades: Optional[str] = None
    ativo: bool = True
    # Fotos agora são um mapa (dict) para flexibilidade
    fotos: dict[str, str] = Field({}, description="URLs das fotos em diferentes tamanhos (ex: {'original': 'url', 'thumbnail': 'url'}).")

class ProfissionalCreate(ProfissionalBase):
    pass

class ProfissionalResponse(ProfissionalBase):
    id: str = Field(..., description="ID do documento do profissional no Firestore.")
    email: EmailStr = Field(..., description="E-mail do profissional (vinculado à sua conta de usuário).") # <-- ADICIONAR ESTA LINHA
    # Adicionamos os serviços aqui para carregar o perfil completo de um profissional
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
    id: str = Field(..., description="ID do documento do serviço no Firestore.")

class ServicoUpdate(BaseModel):
    nome: Optional[str] = None
    descricao: Optional[str] = None
    preco: Optional[float] = None
    duracao_minutos: Optional[int] = None

# =================================================================================
# SCHEMAS DE AGENDAMENTOS (Fortemente Desnormalizado)
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
    
    # --- Dados Desnormalizados (para evitar múltiplas leituras) ---
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
# SCHEMAS DE INTERAÇÕES (Postagens, Comentários, etc.)
# =================================================================================

# --- Postagens (Antigo Feed) ---
class PostagemCreate(BaseModel):
    negocio_id: str
    profissional_id: str
    titulo: str
    descricao: Optional[str] = None
    # Fotos agora são um mapa (dict) para flexibilidade
    fotos: dict[str, str] = Field(..., description="URLs da postagem em diferentes tamanhos.")

class PostagemResponse(PostagemCreate):
    id: str
    data_postagem: datetime
    # Desnormalizado para exibir no feed sem consultas extras
    profissional_nome: str
    profissional_foto_thumbnail: Optional[str] = None
    # Contadores podem ser atualizados via transações ou functions
    total_curtidas: int = 0
    total_comentarios: int = 0
    curtido_pelo_usuario: bool = Field(False, description="Indica se o usuário autenticado curtiu esta postagem.")

# --- Comentários ---
class ComentarioCreate(BaseModel):
    negocio_id: str
    postagem_id: str
    texto: str

class ComentarioResponse(ComentarioCreate):
    id: str
    data: datetime
    # Desnormalizado
    cliente_id: str
    cliente_nome: str

# --- Avaliações ---
class AvaliacaoCreate(BaseModel):
    negocio_id: str
    profissional_id: str
    nota: int = Field(..., ge=1, le=5)
    comentario: Optional[str] = None

class AvaliacaoResponse(AvaliacaoCreate):
    id: str
    data: datetime
    # Desnormalizado
    cliente_id: str
    cliente_nome: str

# =================================================================================
# SCHEMAS DE MÉDICOS (Módulo Clínico)
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

# =================================================================================
# SCHEMAS DE DISPONIBILIDADE (HORÁRIOS E BLOQUEIOS)
# =================================================================================

class HorarioTrabalho(BaseModel):
    dia_semana: int # 0=Seg, 6=Dom
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
    data_agendamento: datetime = Field(..., description="Data e hora em que a notificação deve ser enviada.")

class NotificacaoAgendadaResponse(NotificacaoAgendadaCreate):
    id: str
    status: str = "agendada"
    criado_em: datetime
    criado_por_uid: str # Firebase UID do enfermeiro que agendou

# =================================================================================
# SCHEMAS DA FICHA DO PACIENTE (Módulo Clínico)
# =================================================================================

class VinculoCreate(BaseModel):
    paciente_id: str
    enfermeiro_id: str # ID do documento do usuário enfermeiro

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
    consulta_id: Optional[str] = Field(None, description="ID da consulta à qual o exame está vinculado.")

class ExameCreate(ExameBase):
    pass

class ExameResponse(ExameBase):
    id: str
    consulta_id: Optional[str] = Field(None, description="ID da consulta à qual o exame está vinculado.")

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
    consulta_id: Optional[str] = Field(None, description="ID da consulta à qual a medicação está vinculada.")

class MedicacaoCreate(MedicacaoBase):
    data_criacao: datetime = Field(default_factory=datetime.utcnow) # Adicionado para filtro de plano ativo
    pass

class MedicacaoResponse(MedicacaoBase):
    id: str
    data_criacao: datetime # Adicionado para filtro de plano ativo
    consulta_id: Optional[str] = Field(None, description="ID da consulta à qual a medicação está vinculada.")

class MedicacaoUpdate(BaseModel):
    nome_medicamento: Optional[str] = None
    dosagem: Optional[str] = None
    instrucoes: Optional[str] = None

class ChecklistItemBase(BaseModel):
    negocio_id: str
    paciente_id: str
    descricao_item: str
    concluido: bool = False
    consulta_id: Optional[str] = Field(None, description="ID da consulta à qual o item do checklist está vinculado.")

class ChecklistItemCreate(ChecklistItemBase):
    data_criacao: datetime = Field(default_factory=datetime.utcnow) # Adicionado para filtro de plano ativo
    pass

class ChecklistItemResponse(ChecklistItemBase):
    id: str
    data_criacao: datetime # Adicionado para filtro de plano ativo
    consulta_id: Optional[str] = Field(None, description="ID da consulta à qual o item do checklist está vinculado.")

class ChecklistItemUpdate(BaseModel):
    descricao_item: Optional[str] = None
    concluido: Optional[bool] = None

class OrientacaoBase(BaseModel):
    negocio_id: str
    paciente_id: str
    titulo: str
    conteudo: str
    consulta_id: Optional[str] = Field(None, description="ID da consulta à qual a orientação está vinculada.")

class OrientacaoCreate(OrientacaoBase):
    data_criacao: datetime = Field(default_factory=datetime.utcnow) # Adicionado para filtro de plano ativo
    pass

class OrientacaoResponse(OrientacaoBase):
    id: str
    data_criacao: datetime # Adicionado para filtro de plano ativo
    consulta_id: Optional[str] = Field(None, description="ID da consulta à qual a orientação está vinculada.")

class OrientacaoUpdate(BaseModel):
    titulo: Optional[str] = None
    conteudo: Optional[str] = None

class FichaCompletaResponse(BaseModel):
    consultas: List[ConsultaResponse]
    exames: List[ExameResponse]
    medicacoes: List[MedicacaoResponse]
    checklist: List[ChecklistItemResponse]
    orientacoes: List[OrientacaoResponse]


# --- NOVO BLOCO DE CÓDIGO AQUI ---
# =================================================================================
# SCHEMAS DO DIÁRIO DO TÉCNICO
# =================================================================================

class DiarioTecnicoBase(BaseModel):
    negocio_id: str
    paciente_id: str
    anotacao_geral: str = Field(..., description="Anotação principal sobre o acompanhamento.")
    medicamentos: Optional[str] = Field(None, description="Observações sobre medicamentos.")
    atividades: Optional[str] = Field(None, description="Observações sobre atividades realizadas.")
    intercorrencias: Optional[str] = Field(None, description="Registro de qualquer intercorrência.")
    # Adicione outros campos que julgar necessário

class DiarioTecnicoCreate(DiarioTecnicoBase):
    pass

class DiarioTecnicoResponse(DiarioTecnicoBase):
    id: str
    data_ocorrencia: datetime = Field(..., description="Data e hora em que o registro foi feito.")
    tecnico_id: str = Field(..., description="ID do usuário técnico que fez o registro.")
    tecnico_nome: str = Field(..., description="Nome do técnico que fez o registro (desnormalizado).")

class DiarioTecnicoUpdate(BaseModel):
    anotacao_geral: Optional[str] = None
    medicamentos: Optional[str] = None
    atividades: Optional[str] = None
    intercorrencias: Optional[str] = None
    # --- FIM DO NOVO BLOCO DE CÓDIGO ---

# --- NOVO BLOCO DE CÓDIGO AQUI ---
# =================================================================================
# SCHEMAS DA PESQUISA DE SATISFAÇÃO
# =================================================================================

class RespostaItem(BaseModel):
    pergunta_id: str
    pergunta_texto: str # Desnormalizado para facilitar a exibição
    resposta: str # Pode ser uma nota de 1 a 5, ou um texto, dependendo do tipo da pergunta

class PesquisaEnviadaCreate(BaseModel):
    negocio_id: str
    paciente_id: str
    modelo_pesquisa_id: str # ID do modelo de pesquisa que está sendo respondido

class PesquisaEnviadaResponse(PesquisaEnviadaCreate):
    id: str
    data_envio: datetime
    data_resposta: Optional[datetime] = None
    status: str = Field("pendente", description="Status da pesquisa: 'pendente' ou 'respondida'.")
    respostas: List[RespostaItem] = []

class SubmeterPesquisaRequest(BaseModel):
    respostas: List[RespostaItem]
# --- FIM DO NOVO BLOCO DE CÓDIGO ---

# --- NOVOS SCHEMAS AQUI ---
class TecnicosVincularRequest(BaseModel):
    tecnicos_ids: List[str] = Field(..., description="Lista de IDs de usuários dos técnicos a serem vinculados.")

class SupervisorVincularRequest(BaseModel):
    supervisor_id: str = Field(..., description="ID do usuário (documento) do enfermeiro supervisor.")

# Schemas para a nova funcionalidade de Auditoria de Leitura
class ConfirmacaoLeituraCreate(BaseModel):
    usuario_id: str = Field(..., description="ID do usuário técnico que está confirmando a leitura.")
    ip_origem: Optional[str] = Field(None, description="Endereço IP do cliente, se disponível.")

class ConfirmacaoLeituraResponse(ConfirmacaoLeituraCreate):
    id: str
    paciente_id: str
    data_confirmacao: datetime

# Schemas para a nova funcionalidade de Diário Estruturado
class SinaisVitaisConteudo(BaseModel):
    pressao_sistolica: Optional[int] = None
    pressao_diastolica: Optional[int] = None
    temperatura: Optional[float] = None
    batimentos_cardiacos: Optional[int] = None
    saturacao_oxigenio: Optional[float] = None

class MedicacaoConteudo(BaseModel):
    nome: str
    dose: str
    status: str = Field(..., description="Status da administração: 'administrado', 'recusado', 'pendente'.")
    observacoes: Optional[str] = None

class AnotacaoConteudo(BaseModel):
    categoria: str = Field(..., description="Categoria da anotação (ex: 'Queixa do Paciente', 'Ocorrência', 'Evolução').")
    descricao: str

# Use Union para permitir diferentes tipos de conteúdo
RegistroDiarioConteudo = Union[SinaisVitaisConteudo, MedicacaoConteudo, AnotacaoConteudo]

class RegistroDiarioCreate(BaseModel):
    tipo: str = Field(..., description="O tipo do registro (ex: 'sinais_vitais', 'medicacao', 'anotacao').")
    conteudo: RegistroDiarioConteudo

class RegistroDiarioResponse(RegistroDiarioCreate):
    id: str
    paciente_id: str
    tecnico_id: str
    data_registro: datetime

# Schemas para a nova funcionalidade de Checklist Diário
class ChecklistItemDiarioResponse(BaseModel):
    id: str
    descricao: str
    concluido: bool

class ChecklistItemDiarioUpdate(BaseModel):
    concluido: bool

# Schemas do Plano de Cuidado (modelo hipotético)
# Note: o modelo real de um plano de cuidado teria que ser definido em conjunto
class PlanoCuidado(BaseModel):
    id: str
    negocio_id: str
    paciente_id: str
    modelo_checklist_id: Optional[str] = Field(None, description="ID do modelo de checklist para geração diária.")

# --- FIM DOS NOVOS SCHEMAS ---

# CORREÇÃO: Usa o método model_rebuild() do Pydantic V2 para resolver as referências
ProfissionalResponse.model_rebuild()