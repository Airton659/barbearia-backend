from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from .database import Base

class Usuario(Base):
    __tablename__ = "usuarios"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    senha_hash = Column(String, nullable=False)
    tipo = Column(String, default="cliente")  # cliente ou admin

    agendamentos = relationship("Agendamento", back_populates="usuario")


class Barbeiro(Base):
    __tablename__ = "barbeiros"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome = Column(String, nullable=False)
    especialidades = Column(String)
    foto = Column(String)
    ativo = Column(Boolean, default=True)

    agendamentos = relationship("Agendamento", back_populates="barbeiro")


class Agendamento(Base):
    __tablename__ = "agendamentos"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"))
    barbeiro_id = Column(UUID(as_uuid=True), ForeignKey("barbeiros.id"))
    data_hora = Column(DateTime, nullable=False)
    status = Column(String, default="pendente")

    usuario = relationship("Usuario", back_populates="agendamentos")
    barbeiro = relationship("Barbeiro", back_populates="agendamentos")
