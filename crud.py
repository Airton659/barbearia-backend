from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, and_
import models, schemas
from passlib.hash import bcrypt
import uuid
from datetime import datetime


# --------- USUÁRIOS ---------

def criar_usuario(db: Session, usuario: schemas.UsuarioCreate):
    senha_hash = bcrypt.hash(usuario.senha)
    novo_usuario = models.Usuario(
        id=uuid.uuid4(),
        nome=usuario.nome,
        email=usuario.email,
        senha_hash=senha_hash
    )
    db.add(novo_usuario)
    db.commit()
    db.refresh(novo_usuario)
    return novo_usuario


def buscar_usuario_por_email(db: Session, email: str):
    return db.query(models.Usuario).filter(models.Usuario.email == email).first()


def autenticar_usuario(db: Session, email: str, senha: str):
    usuario = buscar_usuario_por_email(db, email)
    if not usuario or not usuario.verificar_senha(senha):
        return None
    return usuario


# --------- BARBEIROS ---------

# Alteração 1: Adicionado joinedload para otimizar a busca do nome do usuário
def listar_barbeiros(db: Session):
    return db.query(models.Barbeiro).options(joinedload(models.Barbeiro.usuario)).filter(models.Barbeiro.ativo == True).all()

# Alteração 2: A função agora recebe o usuario_id para associar corretamente
def criar_barbeiro(db: Session, barbeiro: schemas.BarbeiroCreate, usuario_id: uuid.UUID):
    novo_barbeiro = models.Barbeiro(
        id=uuid.uuid4(),
        usuario_id=usuario_id,  # Associa o ID do usuário
        # O campo 'nome' foi removido pois não existe no modelo Barbeiro
        especialidades=barbeiro.especialidades,
        foto=barbeiro.foto,
        ativo=barbeiro.ativo
    )
    db.add(novo_barbeiro)
    db.commit()
    db.refresh(novo_barbeiro)
    return novo_barbeiro

# Alteração 3: Corrigido o filtro para buscar por 'usuario_id'
def buscar_barbeiro_por_usuario_id(db: Session, usuario_id: uuid.UUID):
    return db.query(models.Barbeiro).filter(models.Barbeiro.usuario_id == usuario_id).first()


# --------- AGENDAMENTOS ---------

# Alteração 4: Função recebe usuario_id para segurança
def criar_agendamento(db: Session, agendamento: schemas.AgendamentoCreate, usuario_id: uuid.UUID):
    novo_agendamento = models.Agendamento(
        id=uuid.uuid4(),
        usuario_id=usuario_id, # Usa o ID do usuário logado
        barbeiro_id=agendamento.barbeiro_id,
        data_hora=agendamento.data_hora
    )
    db.add(novo_agendamento)
    db.commit()
    db.refresh(novo_agendamento)
    return novo_agendamento


def listar_agendamentos_por_usuario(db: Session, usuario_id: uuid.UUID):
    return db.query(models.Agendamento).filter(models.Agendamento.usuario_id == usuario_id).all()

def listar_agendamentos_por_barbeiro(db: Session, barbeiro_id: uuid.UUID):
    return db.query(models.Agendamento).filter(models.Agendamento.barbeiro_id == barbeiro_id).all()


# --------- POSTAGENS ---------

# Alteração 5: Função recebe barbeiro_id para segurança
def criar_postagem(db: Session, postagem: schemas.PostagemCreate, barbeiro_id: uuid.UUID):
    nova_postagem = models.Postagem(
        id=uuid.uuid4(),
        barbeiro_id=barbeiro_id, # Usa o ID do barbeiro logado
        titulo=postagem.titulo,
        descricao=postagem.descricao,
        foto_url=postagem.foto_url,
        publicada=postagem.publicada,
        data_postagem=datetime.utcnow()
    )
    db.add(nova_postagem)
    db.commit()
    db.refresh(nova_postagem)
    return nova_postagem


def listar_feed(db: Session, limit=10, offset=0):
    return db.query(models.Postagem)\
        .filter(models.Postagem.publicada == True)\
        .order_by(models.Postagem.data_postagem.desc())\
        .offset(offset).limit(limit).all()


def buscar_postagem_por_id(db: Session, postagem_id: uuid.UUID):
    return db.query(models.Postagem).filter(models.Postagem.id == postagem_id).first()


# --------- CURTIDAS ---------

def toggle_curtida(db: Session, usuario_id: uuid.UUID, postagem_id: uuid.UUID):
    curtida = db.query(models.Curtida).filter(
        and_(
            models.Curtida.usuario_id == usuario_id,
            models.Curtida.postagem_id == postagem_id
        )
    ).first()

    if curtida:
        db.delete(curtida)
        db.commit()
        return None
    else:
        nova = models.Curtida(
            id=uuid.uuid4(),
            usuario_id=usuario_id,
            postagem_id=postagem_id,
            data=datetime.utcnow()
        )
        db.add(nova)
        db.commit()
        db.refresh(nova)
        return nova


# --------- COMENTÁRIOS ---------

# Alteração 6: Função recebe usuario_id para segurança
def criar_comentario(db: Session, comentario: schemas.ComentarioCreate, usuario_id: uuid.UUID):
    novo_comentario = models.Comentario(
        id=uuid.uuid4(),
        usuario_id=usuario_id, # Usa o ID do usuário logado
        postagem_id=comentario.postagem_id,
        texto=comentario.texto,
        data=datetime.utcnow()
    )
    db.add(novo_comentario)
    db.commit()
    db.refresh(novo_comentario)
    return novo_comentario


def listar_comentarios(db: Session, postagem_id: uuid.UUID):
    return db.query(models.Comentario)\
        .filter(models.Comentario.postagem_id == postagem_id)\
        .order_by(models.Comentario.data.desc()).all()


# --------- AVALIAÇÕES ---------

# Alteração 7: Função recebe usuario_id para segurança
def criar_avaliacao(db: Session, avaliacao: schemas.AvaliacaoCreate, usuario_id: uuid.UUID):
    nova = models.Avaliacao(
        id=uuid.uuid4(),
        usuario_id=usuario_id, # Usa o ID do usuário logado
        barbeiro_id=avaliacao.barbeiro_id,
        nota=avaliacao.nota,
        comentario=avaliacao.comentario,
        data=datetime.utcnow()
    )
    db.add(nova)
    db.commit()
    db.refresh(nova)
    return nova


def listar_avaliacoes_barbeiro(db: Session, barbeiro_id: uuid.UUID):
    return db.query(models.Avaliacao)\
        .filter(models.Avaliacao.barbeiro_id == barbeiro_id)\
        .order_by(models.Avaliacao.data.desc()).all()


# --------- PERFIL DO BARBEIRO ---------

def obter_perfil_barbeiro(db: Session, barbeiro_id: uuid.UUID):
    # Usando o joinedload para já carregar o nome do usuário junto
    barbeiro = db.query(models.Barbeiro).options(joinedload(models.Barbeiro.usuario)).filter(models.Barbeiro.id == barbeiro_id).first()
    if not barbeiro:
        return {} # Retorna um dicionário vazio se o barbeiro não for encontrado
    
    avaliacoes = listar_avaliacoes_barbeiro(db, barbeiro_id)
    postagens = db.query(models.Postagem).filter(models.Postagem.barbeiro_id == barbeiro_id).all()

    # Monta a resposta do perfil
    perfil_barbeiro = schemas.BarbeiroResponse.from_orm(barbeiro)
    # Atribui o nome do usuário manualmente, caso o from_orm não pegue (depende da config)
    perfil_barbeiro.nome = barbeiro.usuario.nome
    
    return {
        "barbeiro": perfil_barbeiro,
        "avaliacoes": avaliacoes,
        "postagens": postagens
    }