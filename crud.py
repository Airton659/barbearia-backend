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

# --- FUNÇÃO ATUALIZADA: CANCELAR AGENDAMENTO (AGORA EXCLUI) ---
def cancelar_agendamento(db: Session, agendamento_id: uuid.UUID, usuario_id: uuid.UUID) -> Optional[models.Agendamento]:
    """
    Cancela (agora exclui) um agendamento. Permite exclusão apenas pelo usuário que agendou.
    Retorna o agendamento excluído ou None se não encontrado/não autorizado.
    """
    agendamento = db.query(models.Agendamento).filter(models.Agendamento.id == agendamento_id).first()
    
    if not agendamento:
        return None # Agendamento não encontrado
    
    # Verifica se o usuário logado é o dono do agendamento
    if str(agendamento.usuario_id) != str(usuario_id):
        return None # Usuário não autorizado
        
    # ALTERAÇÃO AQUI: Exclui o agendamento em vez de apenas mudar o status
    db.delete(agendamento)
    db.commit()
    return agendamento # Retorna o objeto excluído para confirmação


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

# ALTERAÇÃO AQUI: Modificar listar_feed para incluir curtidas
def listar_feed(db: Session, limit: int = 10, offset: int = 0, usuario_id_logado: Optional[uuid.UUID] = None) -> List[schemas.PostagemResponse]:
    # Carregamos a relação 'barbeiro' e 'usuario' do barbeiro
    query = db.query(models.Postagem)\
        .options(joinedload(models.Postagem.barbeiro).joinedload(models.Barbeiro.usuario))\
        .filter(models.Postagem.publicada == True)\
        .order_by(models.Postagem.data_postagem.desc())\
        .offset(offset)\
        .limit(limit)
    
    postagens_db = query.all()
    
    postagens_response = []
    for postagem in postagens_db:
        # ATENÇÃO AQUI: Passamos APENAS os atributos escalares para model_validate
        # para evitar o conflito com a relação 'curtidas' do SQLAlchemy.
        post_response = schemas.PostagemResponse(
            id=postagem.id,
            barbeiro_id=postagem.barbeiro_id,
            titulo=postagem.titulo,
            descricao=postagem.descricao,
            foto_url_original=postagem.foto_url_original,
            foto_url_medium=postagem.foto_url_medium,
            foto_url_thumbnail=postagem.foto_url_thumbnail,
            data_postagem=postagem.data_postagem,
            publicada=postagem.publicada,
            # curtido_pelo_usuario e curtidas serão preenchidos abaixo
        )
        
        # Preenche o objeto barbeiro na resposta da postagem
        if postagem.barbeiro:
            post_response.barbeiro = schemas.BarbeiroParaPostagem(
                id=postagem.barbeiro.id,
                nome=postagem.barbeiro.usuario.nome,
                foto_thumbnail=postagem.barbeiro.foto_thumbnail
            )

        # Consulta o número total de curtidas para esta postagem
        total_curtidas = db.query(func.count(models.Curtida.id)).filter(models.Curtida.postagem_id == postagem.id).scalar()
        post_response.curtidas = total_curtidas # Preenche o campo curtidas com a contagem

        # Verifica se o usuário logado curtiu esta postagem
        if usuario_id_logado:
            curtida_existente = db.query(models.Curtida).filter(
                and_(
                    models.Curtida.usuario_id == usuario_id_logado,
                    models.Curtida.postagem_id == postagem.id
                )
            ).first()
            post_response.curtido_pelo_usuario = bool(curtida_existente)
        else:
            post_response.curtido_pelo_usuario = False # Se não houver usuário logado, não está curtido
            
        postagens_response.append(post_response)
        
    return postagens_response


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
    # ALTERAÇÃO AQUI: Carrega os comentários e o usuário associado em uma única consulta
    comentarios_db = db.query(models.Comentario)\
        .options(joinedload(models.Comentario.usuario))\
        .filter(models.Comentario.postagem_id == postagem_id)\
        .order_by(models.Comentario.data.desc())\
        .all()
    
    # Mapeia para o schema de resposta, preenchendo os detalhes do usuário
    comentarios_response = []
    for comentario in comentarios_db:
        com_response = schemas.ComentarioResponse.model_validate(comentario)
        if comentario.usuario:
            com_response.usuario = schemas.UsuarioParaAgendamento(
                id=comentario.usuario.id,
                nome=comentario.usuario.nome
            )
        comentarios_response.append(com_response)
        
    return comentarios_response

# NOVA FUNÇÃO: Deletar comentário
def deletar_comentario(db: Session, comentario_id: uuid.UUID, usuario_id: uuid.UUID) -> Optional[models.Comentario]:
    """
    Deleta um comentário. Apenas o usuário que o criou pode deletá-lo.
    Retorna o comentário deletado ou None se não encontrado/não autorizado.
    """
    comentario = db.query(models.Comentario).filter(models.Comentario.id == comentario_id).first()
    
    if not comentario:
        return None # Comentário não encontrado
    
    # Verifica se o usuário logado é o dono do comentário
    if str(comentario.usuario_id) != str(usuario_id):
        return None # Usuário não autorizado
        
    db.delete(comentario)
    db.commit()
    return comentario # Retorna o objeto deletado para confirmação

# NOVA FUNÇÃO: Deletar Postagem
def deletar_postagem(db: Session, postagem_id: uuid.UUID, barbeiro_id: uuid.UUID) -> Optional[models.Postagem]:
    """
    Deleta uma postagem. Apenas o barbeiro que a criou pode deletá-la.
    Retorna a postagem deletada ou None se não encontrada/não autorizado.
    """
    postagem = db.query(models.Postagem).filter(models.Postagem.id == postagem_id).first()
    
    if not postagem:
        return None # Postagem não encontrada
    
    # Verifica se o barbeiro logado é o autor da postagem
    if str(postagem.barbeiro_id) != str(barbeiro_id):
        return None # Barbeiro não autorizado
        
    db.delete(postagem)
    db.commit()
    return postagem # Retorna o objeto deletado para confirmação


def criar_avaliacao(db: Session, avaliacao: schemas.AvaliacaoCreate, usuario_id: uuid.UUID):
    nova = models.Avaliacao(id=uuid.uuid4(), usuario_id=usuario_id, barbeiro_id=avaliacao.barbeiro_id, nota=avaliacao.nota, comentario=avaliacao.comentario, data=datetime.utcnow())
    db.add(nova)
    db.commit()
    db.refresh(nova)
    return nova

def listar_avaliacoes_barbeiro(db: Session, barbeiro_id: uuid.UUID):
    # Fetch evaluations, eager loading the 'usuario' relationship
    avaliacoes_db = db.query(models.Avaliacao)\
        .options(joinedload(models.Avaliacao.usuario))\
        .filter(models.Avaliacao.barbeiro_id == barbeiro_id)\
        .order_by(models.Avaliacao.data.desc())\
        .all()
    
    # Map to the response schema, explicitly including user data
    avaliacoes_response = []
    for avaliacao in avaliacoes_db:
        # Create an instance of AvaliacaoResponse and populate fields, including nested user
        avaliacao_response = schemas.AvaliacaoResponse(
            id=avaliacao.id,
            usuario_id=avaliacao.usuario_id,
            barbeiro_id=avaliacao.barbeiro_id,
            nota=avaliacao.nota,
            comentario=avaliacao.comentario,
            data=avaliacao.data
        )
        
        # Ensure the 'usuario' object is populated if the relationship exists
        if avaliacao.usuario:
            avaliacao_response.usuario = schemas.UsuarioParaAgendamento(
                id=avaliacao.usuario.id,
                nome=avaliacao.usuario.nome
            )
        avaliacoes_response.append(avaliacao_response)
        
    return avaliacoes_response

def obter_perfil_barbeiro(db: Session, barbeiro_id: uuid.UUID):
    barbeiro = db.query(models.Barbeiro).filter(models.Barbeiro.id == barbeiro_id).first()
    if not barbeiro: return {}
    avaliacoes = listar_avaliacoes_barbeiro(db, barbeiro_id)
    
    # MODIFICATION START (from previous turn, keeping it here for completeness)
    # Fetch postagens and eager load the 'barbeiro' and 'usuario' relationships for proper display
    postagens_db = db.query(models.Postagem)\
        .options(joinedload(models.Postagem.barbeiro).joinedload(models.Barbeiro.usuario))\
        .filter(models.Postagem.barbeiro_id == barbeiro_id)\
        .all()

    processed_postagens = []
    for postagem in postagens_db:
        # Calculate the total number of curtidas for this postagem
        total_curtidas = db.query(func.count(models.Curtida.id)).filter(models.Curtida.postagem_id == postagem.id).scalar()

        # Manually construct PostagemResponse to ensure 'curtidas' is an integer
        post_response = schemas.PostagemResponse(
            id=postagem.id,
            barbeiro_id=postagem.barbeiro_id,
            titulo=postagem.titulo,
            descricao=postagem.descricao,
            foto_url_original=postagem.foto_url_original,
            foto_url_medium=postagem.foto_url_medium,
            foto_url_thumbnail=postagem.foto_url_thumbnail,
            data_postagem=postagem.data_postagem,
            publicada=postagem.publicada,
            curtidas=total_curtidas, # Assign the calculated integer count
            curtido_pelo_usuario=False # Default to False, can be adjusted if user context is available
        )
        
        # Populate the 'barbeiro' object within the postagem response
        if postagem.barbeiro:
            post_response.barbeiro = schemas.BarbeiroParaPostagem(
                id=postagem.barbeiro.id,
                nome=postagem.barbeiro.usuario.nome,
                foto_thumbnail=postagem.barbeiro.foto_thumbnail
            )
        processed_postagens.append(post_response)
    # MODIFICATION END

    servicos = listar_servicos_por_barbeiro(db, barbeiro_id)
    
    return {
        "barbeiro": schemas.BarbeiroResponse.model_validate(barbeiro), # Usar o schema para incluir as URLs
        "avaliacoes": avaliacoes, # Now using the modified 'avaliacoes' list
        "postagens": processed_postagens, # Use the list of processed PostagemResponse objects
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