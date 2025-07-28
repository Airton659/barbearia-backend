from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, Integer, Time
# Alteração 1: Importar a hybrid_property
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from database import Base
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class Usuario(Base):
    __tablename__ = "usuarios"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    senha_hash = Column(String, nullable=False)
    tipo = Column(String, default="cliente")  # cliente ou admin
    
    # --- ALTERAÇÃO AQUI ---
    # Novos campos para o fluxo de recuperação de senha
    reset_token = Column(String, unique=True, nullable=True)
    reset_token_expires = Column(DateTime, nullable=True)


    agendamentos = relationship("Agendamento", back_populates="usuario")
    curtidas = relationship("Curtida", back_populates="usuario")
    comentarios = relationship("Comentario", back_populates="usuario")
    avaliacoes = relationship("Avaliacao", back_populates="usuario")
    barbeiro = relationship("Barbeiro", back_populates="usuario", uselist=False)

    def verificar_senha(self, senha: str) -> bool:
        return pwd_context.verify(senha, self.senha_hash)


class Barbeiro(Base):
    __tablename__ = "barbeiros"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), unique=True, nullable=False)
    especialidades = Column(String)
    foto = Column(String)
    ativo = Column(Boolean, default=True)

    usuario = relationship("Usuario", back_populates="barbeiro", lazy="joined")
    agendamentos = relationship("Agendamento", back_populates="barbeiro")
    postagens = relationship("Postagem", back_populates="barbeiro")
    avaliacoes = relationship("Avaliacao", back_populates="barbeiro")
    
    # NOVOS RELACIONAMENTOS ADICIONADOS
    horarios_trabalho = relationship("HorarioTrabalho", back_populates="barbeiro", cascade="all, delete-orphan")
    bloqueios = relationship("Bloqueio", back_populates="barbeiro", cascade="all, delete-orphan")

    # Alteração 2: Adicionada a hybrid_property
    @hybrid_property
    def nome(self):
        """Retorna o nome do usuário associado ao barbeiro."""
        return self.usuario.nome


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

# --- NOVAS TABELAS PARA DISPONIBILIDADE ---

class HorarioTrabalho(Base):
    __tablename__ = "horarios_trabalho"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    barbeiro_id = Column(UUID(as_uuid=True), ForeignKey("barbeiros.id"), nullable=False)
    # 0 = Segunda-feira, 1 = Terça-feira, ..., 6 = Domingo
    dia_semana = Column(Integer, nullable=False)
    hora_inicio = Column(Time, nullable=False)
    hora_fim = Column(Time, nullable=False)
    
    barbeiro = relationship("Barbeiro", back_populates="horarios_trabalho")


class Bloqueio(Base):
    __tablename__ = "bloqueios"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    barbeiro_id = Column(UUID(as_uuid=True), ForeignKey("barbeiros.id"), nullable=False)
    inicio = Column(DateTime, nullable=False)
    fim = Column(DateTime, nullable=False)
    motivo = Column(String, nullable=True)

    barbeiro = relationship("Barbeiro", back_populates="bloqueios")
