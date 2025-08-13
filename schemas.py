# barbearia-backend/schemas.py (Versão para Firestore Multi-Tenant)

from pydantic import BaseModel, EmailStr, Field
from datetime import datetime, time
from typing import Optional, List

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

class UsuarioCreate(UsuarioBase):
    # No Firestore, o usuário é criado via Firebase Auth, então o backend só sincroniza.
    pass

class UsuarioProfile(UsuarioBase):
    id: str = Field(..., description="ID do documento do usuário no Firestore.")
    # Um usuário pode ser membro de múltiplos negócios (ex: admin de um, cliente de outro)
    roles: dict[str, str] = Field({}, description="Dicionário de negocio_id para role (ex: {'negocio_A': 'admin', 'negocio_B': 'cliente'}).")
    fcm_tokens: List[str] = []
    profissional_id: Optional[str] = Field(None, description="ID do perfil profissional, se o usuário for um profissional ou admin.")

# Schema usado pelo endpoint de sync, agora com o negocio_id opcional
class UsuarioSync(BaseModel):
    nome: str
    email: EmailStr
    firebase_uid: str
    negocio_id: Optional[str] = Field(None, description="ID do negócio ao qual o usuário (cliente) está se cadastrando.")
    codigo_convite: Optional[str] = Field(None, description="Código de convite para se tornar admin de um negócio.")

# Schema para registrar o token de notificação
class FCMTokenUpdate(BaseModel):
    fcm_token: str

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
    # Adicionamos os serviços aqui para carregar o perfil completo de um profissional
    servicos: List['ServicoResponse'] = []

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
    # Fotos também viram um mapa para flexibilidade
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
# SCHEMAS DE DISPONIBILIDADE (Horários e Bloqueios)
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
    mensagem: str
    lida: bool
    data_criacao: datetime
    tipo: Optional[str] = None
    referencia_id: Optional[str] = None

class NotificacaoContagemResponse(BaseModel):
    count: int

# CORREÇÃO: Usa o método model_rebuild() do Pydantic V2 para resolver as referências
ProfissionalResponse.model_rebuild()