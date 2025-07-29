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


# ---------- BARBEIRO ----------

class BarbeiroResponse(BaseModel):
    id: UUID
    nome: str
    especialidades: Optional[str] = Field(None, description="Especialidades do barbeiro", example="Corte masculino, barba")
    foto: Optional[str] = Field(None, description="URL da foto do barbeiro", example="https://cdn.com/foto.jpg")
    ativo: bool
    servicos: List['ServicoResponse'] = [] 

    class Config:
        from_attributes = True

# --- NOVA CLASSE ADICIONADA: DETALHES DO BARBEIRO PARA AGENDAMENTO ---
class BarbeiroParaAgendamento(BaseModel):
    id: UUID
    nome: str
    foto: Optional[str] = Field(None, description="URL da foto do barbeiro", example="https://cdn.com/foto.jpg")

    class Config:
        from_attributes = True

class BarbeiroCreate(BaseModel):
    especialidades: Optional[str] = Field(None, max_length=200, description="Especialidades do barbeiro", example="Corte, Barba, Sobrancelha")
    foto: Optional[str] = Field(None, description="URL da foto", example="https://cdn.com/foto.jpg")
    ativo: bool = Field(default=True, description="Define se o barbeiro está ativo")

class BarbeiroUpdateFoto(BaseModel):
    foto_url: str = Field(..., description="Nova URL da foto do barbeiro")

class BarbeiroUpdate(BaseModel):
    especialidades: Optional[str] = Field(None, max_length=200, description="Novas especialidades do barbeiro")

class BarbeiroPromote(BaseModel):
    especialidades: str = Field(..., description="Especialidades iniciais do barbeiro")
    foto: Optional[str] = Field(None, description="URL da foto inicial do barbeiro")


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
    barbeiro: Optional[BarbeiroParaAgendamento] = None # <--- CAMPO ADICIONADO AQUI!

    class Config:
        from_attributes = True


# ---------- POSTAGEM ----------

class PostagemCreate(BaseModel):
    titulo: str = Field(..., min_length=3, max_length=100, description="Título da postagem", example="Corte degradê com navalha")
    descricao: Optional[str] = Field(None, max_length=300, description="Descrição opcional", example="Esse corte foi feito em 40min com acabamento na navalha.")
    foto_url: str = Field(..., description="URL da foto da postagem", example="https://cdn.com/corte1.jpg")
    publicada: bool = Field(default=True, description="Define se a postagem está publicada")

class PostagemResponse(BaseModel):
    id: UUID
    barbeiro_id: UUID
    titulo: str
    descricao: Optional[str]
    foto_url: str
    data_postagem: datetime
    publicada: bool

    class Config:
        from_attributes = True


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

class ServicoResponse(ServicoBase):
    id: UUID
    barbeiro_id: UUID

    class Config:
        from_attributes = True