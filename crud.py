# barbearia-backend/crud.py

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, and_
import models, schemas
from passlib.hash import bcrypt
import uuid
from datetime import datetime, timedelta, date, time
from typing import Optional, List
import secrets

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
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=1)
    
    usuario.reset_token = token
    usuario.reset_token_expires = expires_at
    
    db.commit()
    db.refresh(usuario)
    return token

def buscar_usuario_por_token_recuperacao(db: Session, token: str):
    return db.query(models.Usuario).filter(
        models.Usuario.reset_token == token,
        models.Usuario.reset_token_expires > datetime.utcnow()
    ).first()

def resetar_senha(db: Session, usuario: models.Usuario, nova_senha: str):
    nova_senha_hash = bcrypt.hash(nova_senha)
    usuario.senha_hash = nova_senha_hash
    
    usuario.reset_token = None
    usuario.reset_token_expires = None
    
    db.commit()
    return usuario

# --- Funções de ADMIN ---

def listar_todos_usuarios(db: Session):
    return db.query(models.Usuario).order_by(models.Usuario.nome).all()

def promover_usuario_para_barbeiro(db: Session, usuario_id: uuid.UUID, info_barbeiro: schemas.BarbeiroPromote):
    usuario = db.query(models.Usuario).filter(models.Usuario.id == usuario_id).first()
    if not usuario:
        return None

    barbeiro_existente = buscar_barbeiro_por_usuario_id(db, usuario_id)
    if barbeiro_existente:
        return barbeiro_existente

    usuario.tipo = "barbeiro"
    
    # O campo 'foto' foi removido de BarbeiroCreate no schemas, então ele não pode ser passado diretamente aqui.
    # A foto será manipulada pelo upload_foto e depois atualizada via atualizar_foto_barbeiro, se necessário.
    barbeiro_data = schemas.BarbeiroCreate(
        especialidades=info_barbeiro.especialidades,
        ativo=True # foto foi removida do schemas.BarbeiroCreate
    )
    novo_barbeiro = criar_barbeiro(db=db, barbeiro=barbeiro_data, usuario_id=usuario_id)
    
    db.commit()
    db.refresh(novo_barbeiro)
    return novo_barbeiro


# --------- BARBEIROS ---------

def listar_barbeiros(db: Session, especialidade: Optional[str] = None) -> List[schemas.BarbeiroResponse]:
    # Carrega os barbeiros com o relacionamento de usuário já unido para o nome
    query = db.query(models.Barbeiro).options(joinedload(models.Barbeiro.usuario)).filter(models.Barbeiro.ativo == True)
    
    if especialidade:
        query = query.filter(models.Barbeiro.especialidades.ilike(f"%{especialidade}%"))
        
    barbeiros_db = query.all()
    
    # Processa cada barbeiro para incluir seus serviços
    barbeiros_com_servicos = []
    for barbeiro in barbeiros_db:
        # Pega os serviços para o barbeiro atual
        servicos_do_barbeiro = listar_servicos_por_barbeiro(db, barbeiro.id)
        
        # Cria uma instância de BarbeiroResponse e preenche os campos, incluindo as novas URLs de foto
        barbeiro_response = schemas.BarbeiroResponse.model_validate(barbeiro)
        barbeiro_response.servicos = [schemas.ServicoResponse.model_validate(s) for s in servicos_do_barbeiro]
        
        barbeiros_com_servicos.append(barbeiro_response)
        
    return barbeiros_com_servicos


def criar_barbeiro(db: Session, barbeiro: schemas.BarbeiroCreate, usuario_id: uuid.UUID):
    novo_barbeiro = models.Barbeiro(
        id=uuid.uuid4(),
        usuario_id=usuario_id,
        especialidades=barbeiro.especialidades,
        # foto foi removida de schemas.BarbeiroCreate, então inicializamos como None
        foto_original=None, 
        foto_medium=None,
        foto_thumbnail=None,
        ativo=barbeiro.ativo
    )
    db.add(novo_barbeiro)
    db.commit()
    db.refresh(novo_barbeiro)
    return novo_barbeiro

def buscar_barbeiro_por_usuario_id(db: Session, usuario_id: uuid.UUID):
    return db.query(models.Barbeiro).options(joinedload(models.Barbeiro.usuario)).filter(models.Barbeiro.usuario_id == usuario_id).first()

# ALTERAÇÃO AQUI: Atualizar para receber todas as URLs de foto
def atualizar_foto_barbeiro(
    db: Session, 
    barbeiro: models.Barbeiro, 
    foto_url_original: str, 
    foto_url_medium: Optional[str] = None, 
    foto_url_thumbnail: Optional[str] = None
):
    barbeiro.foto_original = foto_url_original
    barbeiro.foto_medium = foto_url_medium
    barbeiro.foto_thumbnail = foto_url_thumbnail
    db.commit()
    db.refresh(barbeiro)
    return barbeiro

def atualizar_perfil_barbeiro(db: Session, barbeiro: models.Barbeiro, dados_update: schemas.BarbeiroUpdate):
    if dados_update.especialidades is not None:
        barbeiro.especialidades = dados_update.especialidades
    
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


def listar_agendamentos_por_usuario(db: Session, usuario_id: uuid.UUID) -> List[schemas.AgendamentoResponse]:
    # Carrega os agendamentos, juntando eagermente os detalhes do usuário e do barbeiro
    agendamentos_db = db.query(models.Agendamento)\
        .options(joinedload(models.Agendamento.usuario))\
        .options(joinedload(models.Agendamento.barbeiro).joinedload(models.Barbeiro.usuario))\
        .filter(models.Agendamento.usuario_id == usuario_id)\
        .order_by(models.Agendamento.data_hora.desc())\
        .all()
    
    # Mapeia para o schema de resposta, preenchendo os detalhes do barbeiro
    agendamentos_response = []
    for agendamento in agendamentos_db:
        ag_response = schemas.AgendamentoResponse.model_validate(agendamento)
        # Garante que o objeto barbeiro na resposta inclui nome e foto do usuário associado
        if agendamento.barbeiro:
            ag_response.barbeiro = schemas.BarbeiroParaAgendamento(
                id=agendamento.barbeiro.id,
                nome=agendamento.barbeiro.usuario.nome, # Nome do barbeiro vem do relacionamento com usuário
                foto_thumbnail=agendamento.barbeiro.foto_thumbnail # ALTERAÇÃO AQUI: usar foto_thumbnail
            )
        agendamentos_response.append(ag_response)
        
    return agendamentos_response


def listar_agendamentos_por_barbeiro(db: Session, barbeiro_id: uuid.UUID):
    return db.query(models.Agendamento)\
        .options(joinedload(models.Agendamento.usuario))\
        .filter(models.Agendamento.barbeiro_id == barbeiro_id).all()

# --- NOVA FUNÇÃO ADICIONADA: CANCELAR AGENDAMENTO ---
def cancelar_agendamento(db: Session, agendamento_id: uuid.UUID, usuario_id: uuid.UUID) -> Optional[models.Agendamento]:
    """
    Cancela um agendamento. Permite cancelamento apenas pelo usuário que agendou.
    Retorna o agendamento cancelado ou None se não encontrado/não autorizado.
    """
    agendamento = db.query(models.Agendamento).filter(models.Agendamento.id == agendamento_id).first()
    
    if not agendamento:
        return None # Agendamento não encontrado
    
    # Verifica se o usuário logado é o dono do agendamento
    if str(agendamento.usuario_id) != str(usuario_id):
        return None # Usuário não autorizado
        
    # Altera o status para "cancelado"
    agendamento.status = "cancelado"
    db.commit()
    db.refresh(agendamento)
    return agendamento


# --------- POSTAGENS E INTERAÇÕES ---------

# ALTERAÇÃO AQUI: Atualizar para receber todas as URLs de foto
def criar_postagem(
    db: Session, 
    postagem: schemas.PostagemCreate, 
    barbeiro_id: uuid.UUID,
    foto_url_original: str,
    foto_url_medium: Optional[str] = None,
    foto_url_thumbnail: Optional[str] = None
):
    nova_postagem = models.Postagem(
        id=uuid.uuid4(),
        barbeiro_id=barbeiro_id,
        titulo=postagem.titulo,
        descricao=postagem.descricao,
        foto_url_original=foto_url_original, # Usar a URL original
        foto_url_medium=foto_url_medium, # Novo campo
        foto_url_thumbnail=foto_url_thumbnail, # Novo campo
        publicada=postagem.publicada,
        data_postagem=datetime.utcnow()
    )
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
    servicos = listar_servicos_por_barbeiro(db, barbeiro_id)
    # ALTERAÇÃO AQUI: Retornar o perfil do barbeiro usando o schema BarbeiroResponse para incluir as URLs de foto
    return {
        "barbeiro": schemas.BarbeiroResponse.model_validate(barbeiro), # Usar o schema para incluir as URLs
        "avaliacoes": [schemas.AvaliacaoResponse.model_validate(a) for a in avaliacoes],
        "postagens": [schemas.PostagemResponse.model_validate(p) for p in postagens],
        "servicos": [schemas.ServicoResponse.model_validate(s) for s in servicos]
    }


# --------- DISPONIBILIDADE ---------

def definir_horarios_trabalho(db: Session, barbeiro_id: uuid.UUID, horarios: List[schemas.HorarioTrabalhoCreate]):
    db.query(models.HorarioTrabalho).filter(models.HorarioTrabalho.barbeiro_id == barbeiro_id).delete()
    
    novos_horarios = []
    for horario in horarios:
        novo = models.HorarioTrabalho(id=uuid.uuid4(),barbeiro_id=barbeiro_id,**horario.dict())
        novos_horarios.append(novo)
    
    db.add_all(novos_horarios)
    db.commit()
    return novos_horarios

def listar_horarios_trabalho(db: Session, barbeiro_id: uuid.UUID):
    return db.query(models.HorarioTrabalho).filter(models.HorarioTrabalho.barbeiro_id == barbeiro_id).all()

def criar_bloqueio(db: Session, barbeiro_id: uuid.UUID, bloqueio: schemas.BloqueioCreate):
    novo_bloqueio = models.Bloqueio(id=uuid.uuid4(),barbeiro_id=barbeiro_id,**bloqueio.dict())
    db.add(novo_bloqueio)
    db.commit()
    db.refresh(novo_bloqueio)
    return novo_bloqueio

def deletar_bloqueio(db: Session, bloqueio_id: uuid.UUID, barbeiro_id: uuid.UUID):
    bloqueio = db.query(models.Bloqueio).filter(models.Bloqueio.id == bloqueio_id, models.Bloqueio.barbeiro_id == barbeiro_id).first()
    if bloqueio:
        db.delete(bloqueio)
        db.commit()
        return True
    return False

def calcular_horarios_disponiveis(db: Session, barbeiro_id: uuid.UUID, dia: date, duracao_servico_min: int = 60) -> List[time]:
    dia_semana = dia.weekday()
    horario_trabalho = db.query(models.HorarioTrabalho).filter(models.HorarioTrabalho.barbeiro_id == barbeiro_id, models.HorarioTrabalho.dia_semana == dia_semana).first()

    if not horario_trabalho:
        return []

    slots_disponiveis = []
    hora_atual = datetime.combine(dia, horario_trabalho.hora_inicio)
    hora_fim = datetime.combine(dia, horario_trabalho.hora_fim)
    
    while hora_atual < hora_fim:
        slots_disponiveis.append(hora_atual.time())
        hora_atual += timedelta(minutes=duracao_servico_min)

    agendamentos_no_dia = db.query(models.Agendamento).filter(models.Agendamento.barbeiro_id == barbeiro_id,func.date(models.Agendamento.data_hora) == dia).all()
    
    bloqueios_no_dia = db.query(models.Bloqueio).filter(models.Bloqueio.barbeiro_id == barbeiro_id, func.date(models.Bloqueio.inicio) <= dia, func.date(models.Bloqueio.fim) >= dia).all()

    horarios_ocupados = {ag.data_hora.time() for ag in agendamentos_no_dia}

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

# --------- SERVIÇOS ---------

def criar_servico(db: Session, servico: schemas.ServicoCreate, barbeiro_id: uuid.UUID):
    novo_servico = models.Servico(
        id=uuid.uuid4(),
        barbeiro_id=barbeiro_id,
        **servico.dict()
    )
    db.add(novo_servico)
    db.commit()
    db.refresh(novo_servico)
    return novo_servico

def listar_servicos_por_barbeiro(db: Session, barbeiro_id: uuid.UUID):
    return db.query(models.Servico).filter(models.Servico.barbeiro_id == barbeiro_id).order_by(models.Servico.nome).all()