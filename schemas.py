from pydantic import BaseModel, EmailStr
from uuid import UUID
from datetime import datetime

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
    especialidades: str | None
    foto: str | None
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
