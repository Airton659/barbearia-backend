from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, Integer, Time, Float
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
    # Alterado para nullable=True para usuários do Firebase
    senha_hash = Column(String, nullable=True) 
    tipo = Column(String, default="cliente")  # cliente, barbeiro, admin
    
    reset_token = Column(String, unique=True, nullable=True)
    reset_token_expires = Column(DateTime, nullable=True)
    
    # Alteração: Adicionando a coluna firebase_uid
    firebase_uid = Column(String, unique=True, nullable=True, index=True)


    agendamentos = relationship("Agendamento", back_populates="usuario")
    curtidas = relationship("Curtida", back_populates="usuario")
    comentarios = relationship("Comentario", back_populates="usuario") # <--- Comentario adicionado aqui
    avaliacoes = relationship("Avaliacao", back_populates="usuario")
    barbeiro = relationship("Barbeiro", back_populates="usuario", uselist=False)

    def verificar_senha(self, senha: str) -> bool:
        # A verificação de senha só fará sentido para usuários antigos ou não-Firebase
        if self.senha_hash:
            return pwd_context.verify(senha, self.senha_hash)
        return False


class Barbeiro(Base):
    __tablename__ = "barbeiros"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), unique=True, nullable=False)
    especialidades = Column(String)
    # ALTERAÇÃO AQUI: renomear 'foto' para 'foto_original' e adicionar novos campos
    foto_original = Column(String)
    foto_medium = Column(String) # Novo campo
    foto_thumbnail = Column(String) # Novo campo
    ativo = Column(Boolean, default=True)

    usuario = relationship("Usuario", back_populates="barbeiro", lazy="joined")
    agendamentos = relationship("Agendamento", back_populates="barbeiro")
    postagens = relationship("Postagem", back_populates="barbeiro")
    avaliacoes = relationship("Avaliacao", back_populates="barbeiro")
    
    horarios_trabalho = relationship("HorarioTrabalho", back_populates="barbeiro", cascade="all, delete-orphan")
    bloqueios = relationship("Bloqueio", back_populates="barbeiro", cascade="all, delete-orphan")
    
    # NOVO RELACIONAMENTO PARA SERVIÇOS
    servicos = relationship("Servico", back_populates="barbeiro", cascade="all, delete-orphan")

    @hybrid_property
    def nome(self):
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
    # ALTERAÇÃO AQUI: renomear 'foto_url' para 'foto_url_original' e adicionar novos campos
    foto_url_original = Column(String, nullable=False)
    foto_url_medium = Column(String) # Novo campo
    foto_url_thumbnail = Column(String) # Novo campo
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

    usuario = relationship("Usuario", back_populates="comentarios") # <--- ALTERAÇÃO AQUI: Adiciona o relacionamento com Usuario
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

class HorarioTrabalho(Base):
    __tablename__ = "horarios_trabalho"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    barbeiro_id = Column(UUID(as_uuid=True), ForeignKey("barbeiros.id"), nullable=False)
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

# --- NOVA TABELA PARA SERVIÇOS ---

class Servico(Base):
    __tablename__ = "servicos"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    barbeiro_id = Column(UUID(as_uuid=True), ForeignKey("barbeiros.id"), nullable=False)
    nome = Column(String, nullable=False)
    descricao = Column(String, nullable=True)
    preco = Column(Float, nullable=False)
    duracao_minutos = Column(Integer, nullable=False)

    barbeiro = relationship("Barbeiro", back_populates="servicos")