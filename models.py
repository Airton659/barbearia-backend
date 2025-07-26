from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from database import Base


class Usuario(Base):
    __tablename__ = "usuarios"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    senha_hash = Column(String, nullable=False)
    tipo = Column(String, default="cliente")  # cliente ou admin

    agendamentos = relationship("Agendamento", back_populates="usuario")
    curtidas = relationship("Curtida", back_populates="usuario")
    comentarios = relationship("Comentario", back_populates="usuario")
    avaliacoes = relationship("Avaliacao", back_populates="usuario")


class Barbeiro(Base):
    __tablename__ = "barbeiros"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome = Column(String, nullable=False)
    especialidades = Column(String)
    foto = Column(String)
    ativo = Column(Boolean, default=True)

    agendamentos = relationship("Agendamento", back_populates="barbeiro")
    postagens = relationship("Postagem", back_populates="barbeiro")
    avaliacoes = relationship("Avaliacao", back_populates="barbeiro")


class Agendamento(Base):
    __tablename__ = "agendamentos"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"))
    barbeiro_id = Column(UUID(as_uuid=True), ForeignKey("barbeiros.id"))
    data_hora = Column(DateTime, nullable=False)
    status = Column(String, default="pendente")

    usuario = relationship("Usuario", back_populates="agendamentos")
    barbeiro = relationship("Barbeiro", back_populates="agendamentos")


class Postagem(Base):
    __tablename__ = "postagens"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    barbeiro_id = Column(UUID(as_uuid=True), ForeignKey("barbeiros.id"))
    titulo = Column(String, nullable=False)
    descricao = Column(String)
    foto_url = Column(String, nullable=False)
    data_postagem = Column(DateTime, nullable=False)
    publicada = Column(Boolean, default=True)

    barbeiro = relationship("Barbeiro", back_populates="postagens")
    curtidas = relationship("Curtida", back_populates="postagem")
    comentarios = relationship("Comentario", back_populates="postagem")


class Curtida(Base):
    __tablename__ = "curtidas"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"))
    postagem_id = Column(UUID(as_uuid=True), ForeignKey("postagens.id"))
    data = Column(DateTime, nullable=False)

    usuario = relationship("Usuario", back_populates="curtidas")
    postagem = relationship("Postagem", back_populates="curtidas")


class Comentario(Base):
    __tablename__ = "comentarios"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"))
    postagem_id = Column(UUID(as_uuid=True), ForeignKey("postagens.id"))
    texto = Column(String, nullable=False)
    data = Column(DateTime, nullable=False)

    usuario = relationship("Usuario", back_populates="comentarios")
    postagem = relationship("Postagem", back_populates="comentarios")


class Avaliacao(Base):
    __tablename__ = "avaliacoes"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"))
    barbeiro_id = Column(UUID(as_uuid=True), ForeignKey("barbeiros.id"))
    nota = Column(Integer, nullable=False)
    comentario = Column(String)
    data = Column(DateTime, nullable=False)

    usuario = relationship("Usuario", back_populates="avaliacoes")
    barbeiro = relationship("Barbeiro", back_populates="avaliacoes")
