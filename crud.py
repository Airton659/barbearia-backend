# barbearia-backend/crud.py

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, and_
import models, schemas
from passlib.hash import bcrypt
import uuid
from datetime import datetime, timedelta, date, time
from typing import Optional, List
import secrets
from sqlalchemy.exc import IntegrityError
import logging
from firebase_admin import messaging

# Setup do logger para este módulo
logger = logging.getLogger(__name__)


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

def _obter_total_admins(db: Session) -> int:
    """Função auxiliar para contar o número de usuários 'admin'."""
    return db.query(models.Usuario).filter(models.Usuario.tipo == "admin").count()

# Requisito 1: Lógica de Inicialização do Primeiro Administrador
def _criar_perfil_barbeiro_para_admin(db: Session, usuario: models.Usuario):
    """Função auxiliar para criar um perfil de barbeiro básico para o primeiro admin."""
    # Cria o schema necessário para a função de criação de barbeiro
    barbeiro_data = schemas.BarbeiroCreate(
        especialidades="Admin",
        ativo=True
    )
    # Chama a função de criação de barbeiro diretamente, sem alterar o tipo de usuário novamente
    return criar_barbeiro(db=db, barbeiro=barbeiro_data, usuario_id=usuario.id)

def criar_usuario_firebase(db: Session, nome: str, email: str, firebase_uid: str):
    db_usuario = models.Usuario(
        nome=nome,
        email=email,
        firebase_uid=firebase_uid,
        tipo='cliente'
    )
    try:
        db.add(db_usuario)
        db.commit()
        db.refresh(db_usuario)
        
        # Requisito 1: Lógica de Inicialização do Primeiro Administrador
        total_admins = _obter_total_admins(db)
        if total_admins == 0:
            db_usuario.tipo = "admin"
            db.commit()
            db.refresh(db_usuario)
            _criar_perfil_barbeiro_para_admin(db, db_usuario)

        return db_usuario
    except IntegrityError:
        db.rollback()
        return None

def buscar_usuario_por_email(db: Session, email: str):
    return db.query(models.Usuario).filter(models.Usuario.email == email).first()

def buscar_usuario_por_firebase_uid(db: Session, firebase_uid: str):
    return db.query(models.Usuario).filter(models.Usuario.firebase_uid == firebase_uid).first()

def buscar_usuario_por_id(db: Session, usuario_id: uuid.UUID):
    return db.query(models.Usuario).filter(models.Usuario.id == usuario_id).first()

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

# NOVAS FUNÇÕES PARA FCM
def adicionar_fcm_token(db: Session, usuario: models.Usuario, fcm_token: str):
    """Adiciona um FCM token ao usuário, evitando duplicatas."""
    if usuario.fcm_tokens is None:
        usuario.fcm_tokens = []
    if fcm_token not in usuario.fcm_tokens:
        usuario.fcm_tokens.append(fcm_token)
        db.commit()
        db.refresh(usuario)
    return usuario

def remover_fcm_token(db: Session, usuario: models.Usuario, fcm_token: str):
    """Remove um FCM token inválido do usuário."""
    if usuario.fcm_tokens is not None and fcm_token in usuario.fcm_tokens:
        usuario.fcm_tokens.remove(fcm_token)
        db.commit()
        db.refresh(usuario)
    return usuario

# Requisito 2: Lógica de gerenciamento de permissões
def _criar_perfil_barbeiro(db: Session, usuario: models.Usuario):
    """Cria um perfil de barbeiro com especialidades padrão, se ainda não existir."""
    barbeiro_existente = buscar_barbeiro_por_usuario_id(db, usuario.id)
    if not barbeiro_existente:
        novo_barbeiro = models.Barbeiro(
            id=uuid.uuid4(),
            usuario_id=usuario.id,
            especialidades="Especialidades padrão",
            ativo=True
        )
        db.add(novo_barbeiro)
        db.commit()
        db.refresh(novo_barbeiro)
        return novo_barbeiro
    elif not barbeiro_existente.ativo:
        barbeiro_existente.ativo = True
        db.commit()
        db.refresh(barbeiro_existente)
    return barbeiro_existente

def _desativar_perfil_barbeiro(db: Session, usuario: models.Usuario):
    """Desativa o perfil de barbeiro de um usuário, se ele existir."""
    barbeiro = buscar_barbeiro_por_usuario_id(db, usuario.id)
    if barbeiro and barbeiro.ativo:
        barbeiro.ativo = False
        db.commit()
        db.refresh(barbeiro)
        return barbeiro
    return None

def atualizar_permissao_usuario(db: Session, usuario_alvo: models.Usuario, new_role: str) -> Optional[models.Usuario]:
    """
    Atualiza a permissão de um usuário e gerencia os efeitos colaterais
    na tabela de barbeiros.
    """
    valid_roles = ["cliente", "barbeiro", "admin"]
    if new_role not in valid_roles:
        return None # Indica um papel inválido
    
    old_role = usuario_alvo.tipo
    usuario_alvo.tipo = new_role
    
    if new_role in ["barbeiro", "admin"] and old_role not in ["barbeiro", "admin"]:
        _criar_perfil_barbeiro(db, usuario_alvo)
    
    elif new_role == "cliente" and old_role in ["barbeiro", "admin"]:
        _desativar_perfil_barbeiro(db, usuario_alvo)
        
    db.commit()
    db.refresh(usuario_alvo)
    return usuario_alvo


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
        data_hora=agendamento.data_hora,
        status="pendente" # Adicionado para clareza
    )
    db.add(novo_agendamento)
    db.commit()
    db.refresh(novo_agendamento)

    # --- LÓGICA DE NOTIFICAÇÃO CORRIGIDA ---
    # 1. Busca o barbeiro pelo seu ID para obter o usuario_id associado
    barbeiro = db.query(models.Barbeiro).filter(models.Barbeiro.id == agendamento.barbeiro_id).first()
    
    if barbeiro:
        # 2. Busca o nome do cliente que agendou
        cliente_usuario = buscar_usuario_por_id(db, usuario_id)
        
        if cliente_usuario:
            # 3. Cria a mensagem e salva a notificação no banco para o histórico do barbeiro
            mensagem = f"{cliente_usuario.nome} agendou um horário com você para {agendamento.data_hora.strftime('%d/%m/%Y às %H:%M')}."
            criar_notificacao(db, barbeiro.usuario_id, mensagem, "NOVO_AGENDAMENTO", novo_agendamento.id)

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

def cancelar_agendamento(db: Session, agendamento_id: uuid.UUID, usuario_id: uuid.UUID) -> Optional[models.Agendamento]:
    """
    Cancela (agora exclui) um agendamento. Permite exclusão apenas pelo usuário que agendou.
    NOVO: Envia uma notificação para o barbeiro sobre o cancelamento.
    Retorna o agendamento excluído ou None se não encontrado/não autorizado.
    """
    # Carrega o agendamento e os dados do barbeiro e cliente de uma só vez
    agendamento = db.query(models.Agendamento)\
        .options(
            joinedload(models.Agendamento.barbeiro).joinedload(models.Barbeiro.usuario),
            joinedload(models.Agendamento.usuario)
        )\
        .filter(models.Agendamento.id == agendamento_id).first()

    if not agendamento:
        return None  # Agendamento não encontrado

    if str(agendamento.usuario_id) != str(usuario_id):
        return None  # Usuário não autorizado

    # --- LÓGICA DE NOTIFICAÇÃO ADICIONADA ---
    barbeiro_usuario = agendamento.barbeiro.usuario
    cliente_usuario = agendamento.usuario

    if barbeiro_usuario and cliente_usuario and barbeiro_usuario.fcm_tokens:
        data_formatada = agendamento.data_hora.strftime('%d/%m')
        hora_formatada = agendamento.data_hora.strftime('%H:%M')
        mensagem_body = f"O cliente {cliente_usuario.nome} cancelou o horário das {hora_formatada} do dia {data_formatada}."

        message = messaging.Message(
            data={
                "title": "Agendamento Cancelado",
                "body": mensagem_body,
                "tipo": "AGENDAMENTO_CANCELADO_CLIENTE"
            }
        )

        tokens_a_remover = []
        for token in list(barbeiro_usuario.fcm_tokens):
            message.token = token
            try:
                Messaging(message)
                logger.info(f"Notificação de cancelamento enviada para o token do barbeiro: {token}")
            except Exception as e:
                logger.error(f"Erro ao enviar notificação de cancelamento para o token {token}: {e}")
                if hasattr(e, 'code') and e.code in ['invalid-argument', 'unregistered', 'sender-id-mismatch']:
                    tokens_a_remover.append(token)
        
        if tokens_a_remover:
            for token in tokens_a_remover:
                remover_fcm_token(db, barbeiro_usuario, token)
    # --- FIM DA LÓGICA DE NOTIFICAÇÃO ---
        
    db.delete(agendamento)
    db.commit()
    return agendamento

def cancelar_agendamento_pelo_barbeiro(db: Session, agendamento_id: uuid.UUID, barbeiro_id: uuid.UUID, motivo: Optional[str] = None) -> Optional[models.Agendamento]:
    """
    Permite a um barbeiro cancelar um agendamento, atualizando o status
    e criando uma notificação para o cliente.
    """
    agendamento = db.query(models.Agendamento).filter(
        models.Agendamento.id == agendamento_id,
        models.Agendamento.barbeiro_id == barbeiro_id
    ).first()

    if not agendamento:
        return None

    agendamento.status = "cancelado_pelo_barbeiro"
    
    mensagem = f"Seu agendamento para {agendamento.data_hora.strftime('%d/%m/%Y às %H:%M')} foi cancelado."
    if motivo:
        mensagem += f" Motivo: {motivo}"

    criar_notificacao(
        db,
        usuario_id=agendamento.usuario_id,
        mensagem=mensagem,
        tipo="AGENDAMENTO_CANCELADO",
        referencia_id=agendamento.id
    )
    
    db.commit()
    db.refresh(agendamento)
    return agendamento

# --------- POSTAGENS E INTERAÇÕES ---------

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
        foto_url_original=foto_url_original,
        foto_url_medium=foto_url_medium,
        foto_url_thumbnail=foto_url_thumbnail,
        publicada=postagem.publicada,
        data_postagem=datetime.utcnow()
    )
    db.add(nova_postagem)
    db.commit()
    db.refresh(nova_postagem)

    # Corrigido para construir a resposta manualmente e evitar erro de validação
    return schemas.PostagemResponse(
        id=nova_postagem.id,
        barbeiro_id=nova_postagem.barbeiro_id,
        titulo=nova_postagem.titulo,
        descricao=nova_postagem.descricao,
        foto_url_original=nova_postagem.foto_url_original,
        foto_url_medium=nova_postagem.foto_url_medium,
        foto_url_thumbnail=nova_postagem.foto_url_thumbnail,
        data_postagem=nova_postagem.data_postagem,
        publicada=nova_postagem.publicada,
        curtidas=0,
        curtido_pelo_usuario=False,
        barbeiro=schemas.BarbeiroParaPostagem.model_validate(nova_postagem.barbeiro) if nova_postagem.barbeiro else None
    )


def listar_feed(db: Session, limit: int = 10, offset: int = 0, usuario_id_logado: Optional[uuid.UUID] = None) -> List[schemas.PostagemResponse]:
    # Esta é a função corrigida
    query = db.query(models.Postagem)\
        .options(joinedload(models.Postagem.barbeiro).joinedload(models.Barbeiro.usuario))\
        .filter(models.Postagem.publicada == True)\
        .order_by(models.Postagem.data_postagem.desc())\
        .offset(offset)\
        .limit(limit)
    
    postagens_db = query.all()
    
    postagens_response = []
    for postagem in postagens_db:
        # Calcula o total de curtidas
        total_curtidas = db.query(func.count(models.Curtida.id)).filter(models.Curtida.postagem_id == postagem.id).scalar()
        
        # Verifica se o usuário logado curtiu o post
        curtido_pelo_usuario = False
        if usuario_id_logado:
            curtida_existente = db.query(models.Curtida).filter(
                models.Curtida.usuario_id == usuario_id_logado,
                models.Curtida.postagem_id == postagem.id
            ).first()
            curtido_pelo_usuario = bool(curtida_existente)
        
        # Constrói o dicionário de dados para a validação do Pydantic
        post_data = {
            "id": postagem.id,
            "barbeiro_id": postagem.barbeiro_id,
            "titulo": postagem.titulo,
            "descricao": postagem.descricao,
            "foto_url_original": postagem.foto_url_original,
            "foto_url_medium": postagem.foto_url_medium,
            "foto_url_thumbnail": postagem.foto_url_thumbnail,
            "data_postagem": postagem.data_postagem,
            "publicada": postagem.publicada,
            "curtidas": int(total_curtidas) if total_curtidas is not None else 0,
            "curtido_pelo_usuario": curtido_pelo_usuario,
            "barbeiro": postagem.barbeiro
        }
        
        # Valida os dados para criar o objeto de resposta
        post_response = schemas.PostagemResponse.model_validate(post_data)
        postagens_response.append(post_response)
        
    return postagens_response


def buscar_postagem_por_id(db: Session, postagem_id: uuid.UUID):
    return db.query(models.Postagem).options(joinedload(models.Postagem.barbeiro).joinedload(models.Barbeiro.usuario)).filter(models.Postagem.id == postagem_id).first()

def toggle_curtida(db: Session, usuario_id: uuid.UUID, postagem_id: uuid.UUID):
    postagem = buscar_postagem_por_id(db, postagem_id)
    if not postagem:
        return None

    curtida_existente = db.query(models.Curtida).filter(
        and_(
            models.Curtida.usuario_id == usuario_id,
            models.Curtida.postagem_id == postagem_id
        )
    ).first()

    if curtida_existente:
        db.delete(curtida_existente)
        db.commit()
        return None
    else:
        nova_curtida = models.Curtida(
            id=uuid.uuid4(),
            usuario_id=usuario_id,
            postagem_id=postagem_id,
            data=datetime.utcnow()
        )
        db.add(nova_curtida)

        barbeiro_usuario = postagem.barbeiro.usuario
        cliente_usuario = buscar_usuario_por_id(db, usuario_id)

        if barbeiro_usuario and cliente_usuario and barbeiro_usuario.id != cliente_usuario.id:
            mensagem = f"{cliente_usuario.nome} curtiu sua postagem: \"{postagem.titulo}\"."
            criar_notificacao(
                db,
                usuario_id=barbeiro_usuario.id,
                mensagem=mensagem,
                tipo="NOVA_CURTIDA",
                referencia_id=postagem.id
            )

        db.commit()
        db.refresh(nova_curtida)
        return nova_curtida

def criar_comentario(db: Session, comentario: schemas.ComentarioCreate, usuario_id: uuid.UUID):
    postagem = buscar_postagem_por_id(db, comentario.postagem_id)
    if not postagem:
        return None

    novo_comentario = models.Comentario(
        id=uuid.uuid4(),
        usuario_id=usuario_id,
        postagem_id=comentario.postagem_id,
        texto=comentario.texto,
        data=datetime.utcnow()
    )
    db.add(novo_comentario)

    barbeiro_usuario = postagem.barbeiro.usuario
    cliente_usuario = buscar_usuario_por_id(db, usuario_id)

    if barbeiro_usuario and cliente_usuario and barbeiro_usuario.id != cliente_usuario.id:
        mensagem = f"{cliente_usuario.nome} comentou na sua postagem: \"{comentario.texto[:30]}...\""
        criar_notificacao(
            db,
            usuario_id=barbeiro_usuario.id,
            mensagem=mensagem,
            tipo="NOVO_COMENTARIO",
            referencia_id=postagem.id
        )
        
    db.commit()
    db.refresh(novo_comentario)
    return novo_comentario

def listar_comentarios(db: Session, postagem_id: uuid.UUID):
    comentarios_db = db.query(models.Comentario)\
        .options(joinedload(models.Comentario.usuario))\
        .filter(models.Comentario.postagem_id == postagem_id)\
        .order_by(models.Comentario.data.desc())\
        .all()
    
    return [schemas.ComentarioResponse.model_validate(c) for c in comentarios_db]

def deletar_comentario(db: Session, comentario_id: uuid.UUID, usuario_id: uuid.UUID) -> Optional[models.Comentario]:
    comentario = db.query(models.Comentario).filter(models.Comentario.id == comentario_id).first()
    
    if not comentario or str(comentario.usuario_id) != str(usuario_id):
        return None
        
    db.delete(comentario)
    db.commit()
    return comentario

def deletar_postagem(db: Session, postagem_id: uuid.UUID, barbeiro_id: uuid.UUID) -> Optional[models.Postagem]:
    postagem = db.query(models.Postagem).filter(models.Postagem.id == postagem_id).first()
    
    if not postagem or str(postagem.barbeiro_id) != str(barbeiro_id):
        return None
        
    db.delete(postagem)
    db.commit()
    return postagem


def criar_avaliacao(db: Session, avaliacao: schemas.AvaliacaoCreate, usuario_id: uuid.UUID):
    nova = models.Avaliacao(id=uuid.uuid4(), usuario_id=usuario_id, barbeiro_id=avaliacao.barbeiro_id, nota=avaliacao.nota, comentario=avaliacao.comentario, data=datetime.utcnow())
    db.add(nova)
    db.commit()
    db.refresh(nova)
    return nova

def listar_avaliacoes_barbeiro(db: Session, barbeiro_id: uuid.UUID):
    avaliacoes_db = db.query(models.Avaliacao)\
        .options(joinedload(models.Avaliacao.usuario))\
        .filter(models.Avaliacao.barbeiro_id == barbeiro_id)\
        .order_by(models.Avaliacao.data.desc())\
        .all()
    
    return [schemas.AvaliacaoResponse.model_validate(a) for a in avaliacoes_db]

def obter_perfil_barbeiro(db: Session, barbeiro_id: uuid.UUID):
    barbeiro = db.query(models.Barbeiro).filter(models.Barbeiro.id == barbeiro_id).first()
    if not barbeiro: return {}
    
    avaliacoes = listar_avaliacoes_barbeiro(db, barbeiro_id)
    postagens = listar_feed(db, limit=100, offset=0, usuario_id_logado=barbeiro.usuario_id) # Simples, mas funcional
    servicos = listar_servicos_por_barbeiro(db, barbeiro_id)
    
    return {
        "barbeiro": schemas.BarbeiroResponse.model_validate(barbeiro),
        "avaliacoes": avaliacoes,
        "postagens": postagens,
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

def atualizar_servico(db: Session, servico_id: uuid.UUID, dados_update: schemas.ServicoUpdate, barbeiro_id: uuid.UUID):
    servico = db.query(models.Servico).filter(models.Servico.id == servico_id, models.Servico.barbeiro_id == barbeiro_id).first()
    if not servico:
        return None
    
    update_data = dados_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(servico, key, value)
    
    db.commit()
    db.refresh(servico)
    return servico

def deletar_servico(db: Session, servico_id: uuid.UUID, barbeiro_id: uuid.UUID):
    servico = db.query(models.Servico).filter(models.Servico.id == servico_id, models.Servico.barbeiro_id == barbeiro_id).first()
    if servico:
        db.delete(servico)
        db.commit()
        return True
    return False

# --------- NOTIFICAÇÕES ---------

def criar_notificacao(db: Session, usuario_id: uuid.UUID, mensagem: str, tipo: str, referencia_id: Optional[uuid.UUID] = None):
    nova_notificacao = models.Notificacao(
        id=uuid.uuid4(),
        usuario_id=usuario_id,
        mensagem=mensagem,
        tipo=tipo,
        referencia_id=referencia_id,
        data_criacao=datetime.utcnow()
    )
    db.add(nova_notificacao)
    db.commit()
    db.refresh(nova_notificacao)
    return nova_notificacao

def contar_notificacoes_nao_lidas(db: Session, usuario_id: uuid.UUID) -> int:
    return db.query(models.Notificacao).filter(
        models.Notificacao.usuario_id == usuario_id,
        models.Notificacao.lida == False
    ).count()

def listar_notificacoes(db: Session, usuario_id: uuid.UUID) -> List[models.Notificacao]:
    return db.query(models.Notificacao).filter(
        models.Notificacao.usuario_id == usuario_id
    ).order_by(models.Notificacao.data_criacao.desc()).all()


def marcar_notificacao_como_lida(db: Session, notificacao_id: uuid.UUID, usuario_id: uuid.UUID) -> bool:
    notificacao = db.query(models.Notificacao).filter(
        models.Notificacao.id == notificacao_id,
        models.Notificacao.usuario_id == usuario_id
    ).first()
    
    if notificacao:
        notificacao.lida = True
        db.commit()
        return True
    return False