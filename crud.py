# barbearia-backend/crud.py

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, and_
import models, schemas
from passlib.hash import bcrypt
import uuid
from datetime import datetime, timedelta, date, time # Adicionado date e time
from typing import Optional, List # Adicionado List
import secrets # Adicionado para gerar tokens seguros

# --------- USUÁRIOS ---------

def criar_usuario(db: Session, usuario: schemas.UsuarioCreate):
    senha_hash = bcrypt.hash(usuario.senha)
    novo_usuario = models.Usuario(
        id=uuid.uuid4(),
        nome=usuario.nome,
        email=usuario.email,
        senha_hash=senha_hash,
        tipo='cliente'
    )
    db.add(novo_usuario)
    db.commit()
    db.refresh(novo_usuario)
    return novo_usuario


def buscar_usuario_por_email(db: Session, email: str):
    return db.query(models.Usuario).filter(models.Usuario.email == email).first()

# --- Funções para o fluxo de recuperação de senha ---

def gerar_token_recuperacao(db: Session, usuario: models.Usuario):
    """Gera e salva um token de recuperação de senha para um usuário."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=1)
    
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
    
    usuario.reset_token = None
    usuario.reset_token_expires = None
    
    db.commit()
    return usuario

# --- Funções de ADMIN ---

def listar_todos_usuarios(db: Session):
    """[ADMIN] Retorna uma lista de todos os usuários."""
    return db.query(models.Usuario).order_by(models.Usuario.nome).all()

def promover_usuario_para_barbeiro(db: Session, usuario_id: uuid.UUID, info_barbeiro: schemas.BarbeiroPromote):
    """[ADMIN] Promove um usuário para barbeiro e cria seu perfil."""
    usuario = db.query(models.Usuario).filter(models.Usuario.id == usuario_id).first()
    if not usuario:
        return None

    barbeiro_existente = buscar_barbeiro_por_usuario_id(db, usuario_id)
    if barbeiro_existente:
        return barbeiro_existente

    usuario.tipo = "barbeiro"
    
    barbeiro_data = schemas.BarbeiroCreate(
        especialidades=info_barbeiro.especialidades,
        foto=info_barbeiro.foto,
        ativo=True
    )
    novo_barbeiro = criar_barbeiro(db=db, barbeiro=barbeiro_data, usuario_id=usuario_id)
    
    db.commit()
    db.refresh(novo_barbeiro)
    return novo_barbeiro


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
    return db.query(models.Agendamento)\
        .options(joinedload(models.Agendamento.barbeiro))\
        .filter(models.Agendamento.usuario_id == usuario_id).all()

def listar_agendamentos_por_barbeiro(db: Session, barbeiro_id: uuid.UUID):
    return db.query(models.Agendamento)\
        .options(joinedload(models.Agendamento.usuario))\
        .filter(models.Agendamento.barbeiro_id == barbeiro_id).all()


# --------- POSTAGENS E INTERAÇÕES (O restante do arquivo continua o mesmo até o final) ---------

# ... (todas as funções de Postagens, Curtidas, Comentários, Avaliações e Perfil continuam aqui) ...
def criar_postagem(db: Session, postagem: schemas.PostagemCreate, barbeiro_id: uuid.UUID):
    nova_postagem = models.Postagem(id=uuid.uuid4(),barbeiro_id=barbeiro_id,titulo=postagem.titulo,descricao=postagem.descricao,foto_url=postagem.foto_url,publicada=postagem.publicada,data_postagem=datetime.utcnow())
    db.add(nova_postagem)
    db.commit()
    db.refresh(nova_postagem)
    return nova_postagem

def listar_feed(db: Session, limit=10, offset=0):
    return db.query(models.Postagem).filter(models.Postagem.publicada == True).order_by(models.Postagem.data_postagem.desc()).offset(offset).limit(limit).all()

def buscar_postagem_por_id(db: Session, postagem_id: uuid.UUID):
    return db.query(models.Postagem).filter(models.Postagem.id == postagem_id).first()

def toggle_curtida(db: Session, usuario_id: uuid.UUID, postagem_id: uuid.UUID):
    postagem = buscar_postagem_por_id(db, postagem_id)
    if not postagem: return None
    curtida = db.query(models.Curtida).filter(and_(models.Curtida.usuario_id == usuario_id, models.Curtida.postagem_id == postagem_id)).first()
    if curtida:
        db.delete(curtida)
        db.commit()
        return None
    else:
        nova = models.Curtida(id=uuid.uuid4(), usuario_id=usuario_id, postagem_id=postagem_id, data=datetime.utcnow())
        db.add(nova)
        db.commit()
        db.refresh(nova)
        return nova

def criar_comentario(db: Session, comentario: schemas.ComentarioCreate, usuario_id: uuid.UUID):
    novo_comentario = models.Comentario(id=uuid.uuid4(), usuario_id=usuario_id, postagem_id=comentario.postagem_id, texto=comentario.texto, data=datetime.utcnow())
    db.add(novo_comentario)
    db.commit()
    db.refresh(novo_comentario)
    return novo_comentario

def listar_comentarios(db: Session, postagem_id: uuid.UUID):
    return db.query(models.Comentario).filter(models.Comentario.postagem_id == postagem_id).order_by(models.Comentario.data.desc()).all()

def criar_avaliacao(db: Session, avaliacao: schemas.AvaliacaoCreate, usuario_id: uuid.UUID):
    nova = models.Avaliacao(id=uuid.uuid4(), usuario_id=usuario_id, barbeiro_id=avaliacao.barbeiro_id, nota=avaliacao.nota, comentario=avaliacao.comentario, data=datetime.utcnow())
    db.add(nova)
    db.commit()
    db.refresh(nova)
    return nova

def listar_avaliacoes_barbeiro(db: Session, barbeiro_id: uuid.UUID):
    return db.query(models.Avaliacao).filter(models.Avaliacao.barbeiro_id == barbeiro_id).order_by(models.Avaliacao.data.desc()).all()

def obter_perfil_barbeiro(db: Session, barbeiro_id: uuid.UUID):
    barbeiro = db.query(models.Barbeiro).filter(models.Barbeiro.id == barbeiro_id).first()
    if not barbeiro: return {}
    avaliacoes = listar_avaliacoes_barbeiro(db, barbeiro_id)
    postagens = db.query(models.Postagem).filter(models.Postagem.barbeiro_id == barbeiro_id).all()
    return {"barbeiro": barbeiro, "avaliacoes": avaliacoes, "postagens": postagens}

# --------- DISPONIBILIDADE ---------

def definir_horarios_trabalho(db: Session, barbeiro_id: uuid.UUID, horarios: List[schemas.HorarioTrabalhoCreate]):
    # Apaga os horários antigos para substituir pelos novos
    db.query(models.HorarioTrabalho).filter(models.HorarioTrabalho.barbeiro_id == barbeiro_id).delete()
    
    novos_horarios = []
    for horario in horarios:
        novo = models.HorarioTrabalho(
            id=uuid.uuid4(),
            barbeiro_id=barbeiro_id,
            **horario.dict()
        )
        novos_horarios.append(novo)
    
    db.add_all(novos_horarios)
    db.commit()
    return novos_horarios

def listar_horarios_trabalho(db: Session, barbeiro_id: uuid.UUID):
    return db.query(models.HorarioTrabalho).filter(models.HorarioTrabalho.barbeiro_id == barbeiro_id).all()

def criar_bloqueio(db: Session, barbeiro_id: uuid.UUID, bloqueio: schemas.BloqueioCreate):
    novo_bloqueio = models.Bloqueio(
        id=uuid.uuid4(),
        barbeiro_id=barbeiro_id,
        **bloqueio.dict()
    )
    db.add(novo_bloqueio)
    db.commit()
    db.refresh(novo_bloqueio)
    return novo_bloqueio

def deletar_bloqueio(db: Session, bloqueio_id: uuid.UUID, barbeiro_id: uuid.UUID):
    bloqueio = db.query(models.Bloqueio).filter(
        models.Bloqueio.id == bloqueio_id,
        models.Bloqueio.barbeiro_id == barbeiro_id
    ).first()
    if bloqueio:
        db.delete(bloqueio)
        db.commit()
        return True
    return False

def calcular_horarios_disponiveis(db: Session, barbeiro_id: uuid.UUID, dia: date, duracao_servico_min: int = 60) -> List[time]:
    dia_semana = dia.weekday() # 0=Seg, 1=Ter, ...

    # 1. Encontrar o horário de trabalho para o dia da semana
    horario_trabalho = db.query(models.HorarioTrabalho).filter(
        models.HorarioTrabalho.barbeiro_id == barbeiro_id,
        models.HorarioTrabalho.dia_semana == dia_semana
    ).first()

    if not horario_trabalho:
        return [] # Barbeiro não trabalha neste dia

    # 2. Gerar todos os slots de horário possíveis para o dia
    slots_disponiveis = []
    hora_atual = datetime.combine(dia, horario_trabalho.hora_inicio)
    hora_fim = datetime.combine(dia, horario_trabalho.hora_fim)
    
    while hora_atual < hora_fim:
        slots_disponiveis.append(hora_atual.time())
        hora_atual += timedelta(minutes=duracao_servico_min)

    # 3. Buscar agendamentos e bloqueios para o dia
    agendamentos_no_dia = db.query(models.Agendamento).filter(
        models.Agendamento.barbeiro_id == barbeiro_id,
        func.date(models.Agendamento.data_hora) == dia
    ).all()
    
    bloqueios_no_dia = db.query(models.Bloqueio).filter(
        models.Bloqueio.barbeiro_id == barbeiro_id,
        func.date(models.Bloqueio.inicio) <= dia,
        func.date(models.Bloqueio.fim) >= dia
    ).all()

    horarios_ocupados = {ag.data_hora.time() for ag in agendamentos_no_dia}

    # 4. Remover slots ocupados por agendamentos ou bloqueios
    horarios_finais = []
    for slot in slots_disponiveis:
        if slot in horarios_ocupados:
            continue
        
        slot_datetime = datetime.combine(dia, slot)
        em_bloqueio = False
        for bloqueio in bloqueios_no_dia:
            if bloqueio.inicio <= slot_datetime < bloqueio.fim:
                em_bloqueio = True
                break
        
        if not em_bloqueio:
            horarios_finais.append(slot)
            
    return horarios_finais
