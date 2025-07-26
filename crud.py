from sqlalchemy.orm import Session
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
    if not usuario:
        return None
    if not bcrypt.verify(senha, usuario.senha_hash):
        return None
    return usuario


# --------- BARBEIROS ---------

def listar_barbeiros(db: Session):
    return db.query(models.Barbeiro).filter(models.Barbeiro.ativo == True).all()


# --------- AGENDAMENTOS ---------

def criar_agendamento(db: Session, agendamento: schemas.AgendamentoCreate):
    novo_agendamento = models.Agendamento(
        id=uuid.uuid4(),
        usuario_id=agendamento.usuario_id,
        barbeiro_id=agendamento.barbeiro_id,
        data_hora=agendamento.data_hora
    )
    db.add(novo_agendamento)
    db.commit()
    db.refresh(novo_agendamento)
    return novo_agendamento


# --------- POSTAGENS ---------

def criar_postagem(db: Session, postagem: schemas.PostagemCreate):
    nova_postagem = models.Postagem(
        id=uuid.uuid4(),
        barbeiro_id=postagem.barbeiro_id,
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

def criar_comentario(db: Session, comentario: schemas.ComentarioCreate):
    novo_comentario = models.Comentario(
        id=uuid.uuid4(),
        usuario_id=comentario.usuario_id,
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

def criar_avaliacao(db: Session, avaliacao: schemas.AvaliacaoCreate):
    nova = models.Avaliacao(
        id=uuid.uuid4(),
        usuario_id=avaliacao.usuario_id,
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
    barbeiro = db.query(models.Barbeiro).filter(models.Barbeiro.id == barbeiro_id).first()
    avaliacoes = listar_avaliacoes_barbeiro(db, barbeiro_id)
    postagens = db.query(models.Postagem).filter(models.Postagem.barbeiro_id == barbeiro_id).all()
    return {
        "barbeiro": barbeiro,
        "avaliacoes": avaliacoes,
        "postagens": postagens
    }
