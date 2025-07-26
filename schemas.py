from pydantic import BaseModel, EmailStr
from uuid import UUID
from datetime import datetime
from typing import Optional, List


# ---------- USUÁRIO ----------

class UsuarioCreate(BaseModel):
    nome: str
    email: EmailStr
    senha: str  # plaintext, depois faremos hash


class UsuarioResponse(BaseModel):
    id: UUID
    nome: str
    email: EmailStr
    tipo: str

    class Config:
        orm_mode = True


# ---------- BARBEIRO ----------

class BarbeiroResponse(BaseModel):
    id: UUID
    nome: str
    especialidades: Optional[str] = None
    foto: Optional[str] = None
    ativo: bool

    class Config:
        orm_mode = True


# ---------- AGENDAMENTO ----------

class AgendamentoCreate(BaseModel):
    usuario_id: UUID
    barbeiro_id: UUID
    data_hora: datetime


class AgendamentoResponse(BaseModel):
    id: UUID
    usuario_id: UUID
    barbeiro_id: UUID
    data_hora: datetime
    status: str

    class Config:
        orm_mode = True


# ---------- POSTAGEM ----------

class PostagemCreate(BaseModel):
    barbeiro_id: UUID
    titulo: str
    descricao: Optional[str] = None
    foto_url: str
    publicada: bool = True


class PostagemResponse(BaseModel):
    id: UUID
    barbeiro_id: UUID
    titulo: str
    descricao: Optional[str] = None
    foto_url: str
    data_postagem: datetime
    publicada: bool

    class Config:
        orm_mode = True


# ---------- CURTIDA ----------

class CurtidaResponse(BaseModel):
    id: UUID
    usuario_id: UUID
    postagem_id: UUID
    data: datetime

    class Config:
        orm_mode = True


# ---------- COMENTÁRIO ----------

class ComentarioCreate(BaseModel):
    usuario_id: UUID
    postagem_id: UUID
    texto: str


class ComentarioResponse(BaseModel):
    id: UUID
    usuario_id: UUID
    postagem_id: UUID
    texto: str
    data: datetime

    class Config:
        orm_mode = True


# ---------- AVALIAÇÃO ----------

class AvaliacaoCreate(BaseModel):
    usuario_id: UUID
    barbeiro_id: UUID
    nota: int
    comentario: Optional[str] = None


class AvaliacaoResponse(BaseModel):
    id: UUID
    usuario_id: UUID
    barbeiro_id: UUID
    nota: int
    comentario: Optional[str] = None
    data: datetime

    class Config:
        orm_mode = True


# ---------- PERFIL DO BARBEIRO ----------

class PerfilBarbeiroResponse(BaseModel):
    barbeiro: BarbeiroResponse
    avaliacoes: List[AvaliacaoResponse]
    postagens: List[PostagemResponse]

    class Config:
        orm_mode = True
