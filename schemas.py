# barbearia-backend/schemas.py

from pydantic import BaseModel, EmailStr, Field
from uuid import UUID
from datetime import datetime, time 
from typing import Optional, List


# ---------- USUÁRIO ----------

class UsuarioCreate(BaseModel):
    nome: str = Field(..., min_length=2, max_length=50, description="Nome completo do usuário", example="João da Silva")
    email: EmailStr = Field(..., description="Email do usuário", example="joao@email.com")
    senha: str = Field(..., min_length=6, max_length=100, description="Senha do usuário (mínimo 6 caracteres)", example="senha123")

class UsuarioLogin(BaseModel):
    email: EmailStr = Field(..., description="Email do usuário para login", example="joao@email.com")
    senha: str = Field(..., min_length=6, max_length=100, description="Senha do usuário", example="senha123")

class UsuarioResponse(BaseModel):
    id: UUID
    nome: str
    email: EmailStr
    tipo: str

    class Config:
        from_attributes = True

class UsuarioParaAgendamento(BaseModel):
    id: UUID
    nome: str

    class Config:
        from_attributes = True

class TokenResponse(BaseModel):
    access_token: str = Field(..., description="Token JWT de acesso")
    token_type: str = Field(default="bearer", description="Tipo do token")

class RecuperarSenhaRequest(BaseModel):
    email: EmailStr = Field(..., description="Email do usuário para iniciar a recuperação de senha")

class ResetarSenhaRequest(BaseModel):
    token: str = Field(..., description="Token de reset recebido")
    nova_senha: str = Field(..., min_length=6, max_length=100, description="Nova senha do usuário")

# Novo schema para a resposta do perfil do usuário
class UsuarioProfile(BaseModel):
    id: UUID
    nome: str
    email: EmailStr
    tipo: str
    firebase_uid: Optional[str] = None
    fcm_tokens: List[str] = []

    class Config:
        from_attributes = True

# Novo schema para a criação/sincronização de usuário do Firebase
class UsuarioSync(BaseModel):
    nome: str
    email: EmailStr
    firebase_uid: str

# NOVO SCHEMA PARA O TOKEN FCM
class FCMTokenUpdate(BaseModel):
    fcm_token: str = Field(..., description="Token FCM do dispositivo a ser registrado")
    
# NOVO SCHEMA PARA ATUALIZAÇÃO DE PERMISSÃO DE USUÁRIO
class UsuarioRoleUpdate(BaseModel):
    new_role: str = Field(..., description="Nova permissão do usuário. Valores permitidos: 'cliente', 'barbeiro', 'admin'", example="barbeiro")


# ---------- BARBEIRO ----------

class BarbeiroResponse(BaseModel):
    id: UUID
    nome: str
    especialidades: Optional[str] = Field(None, description="Especialidades do barbeiro", example="Corte masculino, barba")
    foto_original: Optional[str] = Field(None, description="URL da foto original do barbeiro", example="https://cdn.com/foto_original.jpg")
    foto_medium: Optional[str] = Field(None, description="URL da foto média do barbeiro")
    foto_thumbnail: Optional[str] = Field(None, description="URL da foto em miniatura do barbeiro")
    ativo: bool
    servicos: List['ServicoResponse'] = [] 

    class Config:
        from_attributes = True

class BarbeiroParaAgendamento(BaseModel):
    id: UUID
    nome: str
    foto_thumbnail: Optional[str] = Field(None, description="URL da foto em miniatura do barbeiro", example="https://cdn.com/foto_thumb.jpg")

    class Config:
        from_attributes = True

# NOVA CLASSE ADICIONADA: DETALHES DO BARBEIRO PARA POSTAGEM NO FEED
class BarbeiroParaPostagem(BaseModel):
    id: UUID
    nome: str
    foto_thumbnail: Optional[str] = Field(None, description="URL da foto em miniatura do barbeiro", example="https://cdn.com/foto_thumb.jpg")

    class Config:
        from_attributes = True

class BarbeiroCreate(BaseModel):
    especialidades: Optional[str] = Field(None, max_length=200, description="Especialidades do barbeiro", example="Corte, Barba, Sobrancelha")
    ativo: bool = Field(default=True, description="Define se o barbeiro está ativo")

class BarbeiroUpdateFoto(BaseModel):
    foto_url: str = Field(..., description="URL da foto original do barbeiro (para casos específicos de update ou se o frontend enviar apenas uma)")

class BarbeiroUpdate(BaseModel):
    especialidades: Optional[str] = Field(None, max_length=200, description="Novas especialidades do barbeiro")

class BarbeiroPromote(BaseModel):
    especialidades: str = Field(..., description="Especialidades iniciais do barbeiro")
    

# ---------- AGENDAMENTO ----------

class AgendamentoCreate(BaseModel):
    barbeiro_id: UUID = Field(..., description="ID do barbeiro escolhido")
    data_hora: datetime = Field(..., description="Data e hora do agendamento", example="2025-08-01T15:00:00")

class AgendamentoResponse(BaseModel):
    id: UUID
    usuario_id: UUID
    barbeiro_id: UUID
    data_hora: datetime
    status: str
    usuario: UsuarioParaAgendamento
    barbeiro: Optional[BarbeiroParaAgendamento] = None

    class Config:
        from_attributes = True


# ---------- POSTAGEM ----------

class PostagemCreate(BaseModel):
    titulo: str = Field(..., min_length=3, max_length=100, description="Título da postagem", example="Corte degradê com navalha")
    descricao: Optional[str] = Field(None, max_length=300, description="Descrição opcional", example="Esse corte foi feito em 40min com acabamento na navalha.")
    publicada: bool = Field(default=True, description="Define se a postagem está publicada")

class PostagemResponse(BaseModel):
    id: UUID
    barbeiro_id: UUID
    titulo: str
    descricao: Optional[str]
    foto_url_original: str
    foto_url_medium: Optional[str]
    foto_url_thumbnail: Optional[str]
    data_postagem: datetime
    publicada: bool
    curtido_pelo_usuario: Optional[bool] = None
    curtidas: Optional[int] = None
    barbeiro: Optional[BarbeiroParaPostagem] = None # <-- ALTERAÇÃO AQUI: Novo campo para o objeto barbeiro

    class Config:
        from_attributes = True

class PostagemCreateRequest(BaseModel):
    postagem: PostagemCreate
    foto_urls: dict = Field(..., description="Dicionário com as URLs da imagem em diferentes tamanhos (original, medium, thumbnail)", example={"original": "url.original.jpg", "medium": "url.medium.jpg", "thumbnail": "url.thumb.jpg"})


# ---------- CURTIDA ----------

class CurtidaResponse(BaseModel):
    id: UUID
    usuario_id: UUID
    postagem_id: UUID
    data: datetime

    class Config:
        from_attributes = True


# ---------- COMENTÁRIO ----------

class ComentarioCreate(BaseModel):
    postagem_id: UUID = Field(..., description="ID da postagem comentada")
    texto: str = Field(..., min_length=1, max_length=300, description="Texto do comentário", example="Ficou top esse corte!")

class ComentarioResponse(BaseModel):
    id: UUID
    usuario_id: UUID
    postagem_id: UUID
    texto: str
    data: datetime
    usuario: Optional[UsuarioParaAgendamento] = None

    class Config:
        from_attributes = True


# ---------- AVALIAÇÃO ----------

class AvaliacaoCreate(BaseModel):
    barbeiro_id: UUID = Field(..., description="ID do barbeiro avaliado")
    nota: int = Field(..., ge=1, le=5, description="Nota de avaliação de 1 a 5", example=5)
    comentario: Optional[str] = Field(None, max_length=300, description="Comentário opcional sobre a experiência")

class AvaliacaoResponse(BaseModel):
    id: UUID
    usuario_id: UUID
    barbeiro_id: UUID
    nota: int
    comentario: Optional[str]
    data: datetime
    usuario: Optional[UsuarioParaAgendamento] = None

    class Config:
        from_attributes = True


# ---------- PERFIL DO BARBEIRO ----------

class PerfilBarbeiroResponse(BaseModel):
    barbeiro: BarbeiroResponse
    avaliacoes: List[AvaliacaoResponse]
    postagens: List[PostagemResponse]

    class Config:
        from_attributes = True

# ---------- DISPONIBILIDADE ----------

class HorarioTrabalhoBase(BaseModel):
    dia_semana: int = Field(..., ge=0, le=6, description="Dia da semana (0=Seg, 6=Dom)")
    hora_inicio: time = Field(..., description="Hora de início do expediente")
    hora_fim: time = Field(..., description="Hora de fim do expediente")

class HorarioTrabalhoCreate(HorarioTrabalhoBase):
    pass

class HorarioTrabalhoResponse(HorarioTrabalhoBase):
    id: UUID
    barbeiro_id: UUID

    class Config:
        from_attributes = True

class BloqueioBase(BaseModel):
    inicio: datetime = Field(..., description="Início do período de bloqueio")
    fim: datetime = Field(..., description="Fim do período de bloqueio")
    motivo: Optional[str] = Field(None, description="Motivo do bloqueio (opcional)")

class BloqueioCreate(BloqueioBase):
    pass

class BloqueioResponse(BaseModel):
    id: UUID
    barbeiro_id: UUID

    class Config:
        from_attributes = True
        
# ---------- SERVIÇOS ----------

class ServicoBase(BaseModel):
    nome: str = Field(..., max_length=100, description="Nome do serviço", example="Corte Masculino")
    descricao: Optional[str] = Field(None, max_length=300, description="Descrição do serviço")
    preco: float = Field(..., gt=0, description="Preço do serviço em Reais", example=50.00)
    duracao_minutos: int = Field(..., gt=0, description="Duração do serviço em minutos", example=45)

class ServicoCreate(ServicoBase):
    pass

class ServicoUpdate(BaseModel):
    nome: Optional[str] = Field(None, max_length=100)
    descricao: Optional[str] = Field(None, max_length=300)
    preco: Optional[float] = Field(None, gt=0)
    duracao_minutos: Optional[int] = Field(None, gt=0)


class ServicoResponse(BaseModel):
    id: UUID
    barbeiro_id: UUID
    nome: str
    descricao: Optional[str]
    preco: float
    duracao_minutos: int

    class Config:
        from_attributes = True

# ---------- NOTIFICAÇÕES ----------

class NotificacaoResponse(BaseModel):
    id: UUID
    mensagem: str
    lida: bool
    data_criacao: datetime
    tipo: Optional[str] = None
    referencia_id: Optional[UUID] = None

    class Config:
        from_attributes = True

class NotificacaoContagemResponse(BaseModel):
    count: int

class AgendamentoCancelamentoRequest(BaseModel):
    motivo: Optional[str] = Field(None, max_length=200, description="Motivo do cancelamento pelo barbeiro")