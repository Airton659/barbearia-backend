# barbearia-backend/crud.py

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, and_
import models, schemas
from passlib.hash import bcrypt
import uuid
from datetime import datetime, timedelta # Adicionado timedelta
from typing import Optional
import secrets # Adicionado para gerar tokens seguros

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

# --- ALTERAÇÃO AQUI ---
# Novas funções para o fluxo de recuperação de senha

def gerar_token_recuperacao(db: Session, usuario: models.Usuario):
    """Gera e salva um token de recuperação de senha para um usuário."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=1) # O token expira em 1 hora
    
    usuario.reset_token = token
    usuario.reset_token_expires = expires_at
    
    db.commit()
    db.refresh(usuario)
    return token

def buscar_usuario_por_token_recuperacao(db: Session, token: str):
    """Busca um usuário por um token de recuperação válido."""
    return db.query(models.Usuario).filter(
        models.Usuario.reset_token == token,
        models.Usuario.reset_token_expires > datetime.utcnow()
    ).first()

def resetar_senha(db: Session, usuario: models.Usuario, nova_senha: str):
    """Atualiza a senha do usuário e invalida o token de recuperação."""
    nova_senha_hash = bcrypt.hash(nova_senha)
    usuario.senha_hash = nova_senha_hash
    
    # Invalida o token para que não possa ser usado novamente
    usuario.reset_token = None
    usuario.reset_token_expires = None
    
    db.commit()
    return usuario


# --------- BARBEIROS ---------

def listar_barbeiros(db: Session, especialidade: Optional[str] = None):
    query = db.query(models.Barbeiro).options(joinedload(models.Barbeiro.usuario)).filter(models.Barbeiro.ativo == True)
    
    if especialidade:
        query = query.filter(models.Barbeiro.especialidades.ilike(f"%{especialidade}%"))
        
    return query.all()

def criar_barbeiro(db: Session, barbeiro: schemas.BarbeiroCreate, usuario_id: uuid.UUID):
    novo_barbeiro = models.Barbeiro(
        id=uuid.uuid4(),
        usuario_id=usuario_id,
        especialidades=barbeiro.especialidades,
        foto=barbeiro.foto,
        ativo=barbeiro.ativo
    )
    db.add(novo_barbeiro)
    db.commit()
    db.refresh(novo_barbeiro)
    return novo_barbeiro

def buscar_barbeiro_por_usuario_id(db: Session, usuario_id: uuid.UUID):
    return db.query(models.Barbeiro).options(joinedload(models.Barbeiro.usuario)).filter(models.Barbeiro.usuario_id == usuario_id).first()

def atualizar_foto_barbeiro(db: Session, barbeiro: models.Barbeiro, foto_url: str):
    barbeiro.foto = foto_url
    db.commit()
    db.refresh(barbeiro)
    return barbeiro


# --------- AGENDAMENTOS ---------

def criar_agendamento(db: Session, agendamento: schemas.AgendamentoCreate, usuario_id: uuid.UUID):
    novo_agendamento = models.Agendamento(
        id=uuid.uuid4(),
        usuario_id=usuario_id,
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

def criar_postagem(db: Session, postagem: schemas.PostagemCreate, barbeiro_id: uuid.UUID):
    nova_postagem = models.Postagem(
        id=uuid.uuid4(),
        barbeiro_id=barbeiro_id,
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
    postagem = buscar_postagem_por_id(db, postagem_id)
    if not postagem:
        return None

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

def criar_comentario(db: Session, comentario: schemas.ComentarioCreate, usuario_id: uuid.UUID):
    novo_comentario = models.Comentario(
        id=uuid.uuid4(),
        usuario_id=usuario_id,
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

def criar_avaliacao(db: Session, avaliacao: schemas.AvaliacaoCreate, usuario_id: uuid.UUID):
    nova = models.Avaliacao(
        id=uuid.uuid4(),
        usuario_id=usuario_id,
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
    if not barbeiro:
        return {}
    
    avaliacoes = listar_avaliacoes_barbeiro(db, barbeiro_id)
    postagens = db.query(models.Postagem).filter(models.Postagem.barbeiro_id == barbeiro_id).all()
    
    return {
        "barbeiro": barbeiro,
        "avaliacoes": avaliacoes,
        "postagens": postagens
    }
