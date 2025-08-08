# barbearia-backend/main.py
from pydantic import BaseModel
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session, joinedload  # Adicionado joinedload para buscar barbeiro
from sqlalchemy.exc import OperationalError
from typing import List, Optional
import models, schemas, crud
import uuid
import time
import os
import json
from datetime import date, time, timedelta
import logging
# Alteração: Importar a nova dependência de autenticação do Firebase
from auth import get_current_user_firebase, get_current_admin_user
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse
import httpx
from database import get_db, engine
from google.cloud import storage
from PIL import Image
from io import BytesIO
import firebase_admin.messaging

app = FastAPI()

# Adicionar um logger para ajudar no debug
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# AQUI: A variável CLOUD_STORAGE_BUCKET_NAME é definida globalmente
# Vamos manter a definição global, mas garantir a verificação dentro das funções.
CLOUD_STORAGE_BUCKET_NAME_GLOBAL = os.getenv("CLOUD_STORAGE_BUCKET_NAME")

@app.on_event("startup")
def startup():
    max_retries = 5
    retry_delay = 4
    for attempt in range(max_retries):
        try:
            with engine.connect() as connection:
                print("Conexão com o banco de dados bem-sucedida!")
                models.Base.metadata.create_all(bind=engine)
                print("Tabelas criadas com sucesso.")
                break
        except OperationalError as e:
            print(f"Tentativa {attempt + 1} de {max_retries} falhou: {e}")
            if attempt < max_retries - 1:
                print(f"Tentando novamente em {retry_delay} segundos...")
                time.sleep(retry_delay)
            else:
                print("Número máximo de tentativas atingido. A aplicação pode não funcionar.")
                raise e

@app.get("/")
def root():
    return {"mensagem": "API da barbearia funcionando"}


# --------- LOGIN ---------
# Endpoint de login antigo foi removido, pois o app usará o Firebase para autenticação


# --------- USUÁRIOS ---------

@app.post("/usuarios", response_model=schemas.UsuarioResponse)
def criar_usuario(usuario: schemas.UsuarioCreate, db: Session = Depends(get_db)):
    existente = crud.buscar_usuario_por_email(db, usuario.email)
    if existente:
        raise HTTPException(status_code=400, detail="Email já cadastrado")
    return crud.criar_usuario(db, usuario)

# --- Novo endpoint para sincronização de perfil do Firebase ---
@app.post("/users/sync-profile", response_model=schemas.UsuarioProfile)
def sync_user_profile(
    user_data: schemas.UsuarioSync,
    db: Session = Depends(get_db)
):
    # Verifica se já existe um usuário com este firebase_uid
    db_user = crud.buscar_usuario_por_firebase_uid(db, firebase_uid=user_data.firebase_uid)
    if db_user:
        # Se o usuário já existe, retorna os dados existentes
        return db_user
    
    # Se não existe, cria um novo usuário no banco de dados local
    db_user = crud.criar_usuario_firebase(
        db,
        nome=user_data.nome,
        email=user_data.email,
        firebase_uid=user_data.firebase_uid
    )
    return db_user


# --- Novo endpoint para obter perfil do usuário logado ---
@app.get("/me/profile", response_model=schemas.UsuarioProfile)
def get_me_profile(current_user: models.Usuario = Depends(get_current_user_firebase)):
    # A dependência get_current_user_firebase já garante que o usuário existe
    # e está autenticado, então basta retornar o objeto
    return current_user


# --- Endpoints para recuperação de senha ---

@app.post("/recuperar-senha")
def recuperar_senha(request: schemas.RecuperarSenhaRequest, db: Session = Depends(get_db)):
    usuario = crud.buscar_usuario_por_email(db, email=request.email)
    if not usuario:
        return {"mensagem": "Se um usuário com este e-mail existir, um link de recuperação foi enviado."}
    
    token = crud.gerar_token_recuperacao(db, usuario)
    print(f"TOKEN DE RECUPERAÇÃO PARA {usuario.email}: {token}")
    return {"mensagem": "Token de recuperação gerado com sucesso.", "reset_token": token}


@app.post("/resetar-senha")
def resetar_senha(request: schemas.ResetarSenhaRequest, db: Session = Depends(get_db)):
    usuario = crud.buscar_usuario_por_token_recuperacao(db, token=request.token)
    
    if not usuario:
        raise HTTPException(status_code=400, detail="Token inválido ou expirado.")
    
    crud.resetar_senha(db, usuario, nova_senha=request.nova_senha)
    return {"mensagem": "Senha atualizada com sucesso."}

# NOVO ENDPOINT: Registrar o token FCM
@app.post("/me/register-fcm-token", status_code=status.HTTP_200_OK)
def register_fcm_token_endpoint(
    request: schemas.FCMTokenUpdate,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_user_firebase)
):
    crud.adicionar_fcm_token(db, current_user, request.fcm_token)
    return {"message": "FCM token registrado com sucesso."}


# --------- ADMIN ---------

@app.get("/admin/usuarios", response_model=List[schemas.UsuarioResponse])
def admin_listar_usuarios(db: Session = Depends(get_db), admin: models.Usuario = Depends(get_current_admin_user)):
    return crud.listar_todos_usuarios(db)

@app.patch("/admin/users/{user_id}/role", response_model=schemas.UsuarioResponse)
def admin_atualizar_permissao_usuario(
    user_id: uuid.UUID,
    role_update: schemas.UsuarioRoleUpdate,
    db: Session = Depends(get_db),
    admin: models.Usuario = Depends(get_current_admin_user)
):
    usuario_alvo = crud.buscar_usuario_por_id(db, user_id)
    if not usuario_alvo:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")

    if role_update.new_role not in ["cliente", "barbeiro", "admin"]:
        raise HTTPException(status_code=400, detail="Permissão inválida. Use 'cliente', 'barbeiro' ou 'admin'.")

    # Impede que um admin desative a si mesmo.
    if usuario_alvo.id == admin.id and role_update.new_role != "admin":
        raise HTTPException(status_code=403, detail="Você não pode remover sua própria permissão de administrador.")

    usuario_atualizado = crud.atualizar_permissao_usuario(db, usuario_alvo, role_update.new_role)
    if not usuario_atualizado:
        raise HTTPException(status_code=500, detail="Ocorreu um erro ao atualizar a permissão do usuário.")
    
    return usuario_atualizado


# --------- BARBEIROS ---------

@app.get("/barbeiros", response_model=List[schemas.BarbeiroResponse])
def listar_barbeiros(db: Session = Depends(get_db), especialidade: Optional[str] = None):
    return crud.listar_barbeiros(db, especialidade=especialidade)


# --------- AGENDAMENTOS ---------

@app.post("/agendamentos", response_model=schemas.AgendamentoResponse)
async def agendar(
    agendamento: schemas.AgendamentoCreate,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_user_firebase)
):
    novo_agendamento = crud.criar_agendamento(db, agendamento, usuario_id=current_user.id)
    
    barbeiro = db.query(models.Barbeiro).options(joinedload(models.Barbeiro.usuario)).filter(models.Barbeiro.id == agendamento.barbeiro_id).first()
    
    if barbeiro and barbeiro.usuario and barbeiro.usuario.fcm_tokens:
        cliente_nome = current_user.nome if current_user else "Um cliente"
        mensagem_body = f"{cliente_nome} agendou um horário com você para {novo_agendamento.data_hora.strftime('%d/%m/%Y às %H:%M')}."
        
        tokens_a_enviar = list(barbeiro.usuario.fcm_tokens)
        
        for token in tokens_a_enviar:
            try:
                message = firebase_admin.messaging.Message(
                    token=token,
                    data={
                        "title": "Novo Agendamento!",
                        "body": mensagem_body,
                        "tipo": "NOVO_AGENDAMENTO",
                        "agendamento_id": str(novo_agendamento.id)
                    }
                )
                
                # CORREÇÃO AQUI
                response = firebase_admin.Messaging(message)
                logger.info(f"Notificação push enviada para o token: {token}. Response: {response}")

            except firebase_admin.messaging.FirebaseError as e:
                logger.error(f"Erro ao enviar notificação para o token {token}: {e}")
                if e.code in ['invalid-argument', 'unregistered', 'sender-id-mismatch']:
                    logger.warning(f"Removendo token FCM inválido do usuário {barbeiro.usuario.id}: {token}")
                    crud.remover_fcm_token(db, barbeiro.usuario, token)
    
    return novo_agendamento

@app.get("/agendamentos", response_model=List[schemas.AgendamentoResponse])
def listar_agendamentos(
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_user_firebase)
):
    """
    Lista todos os agendamentos do usuário autenticado.
    """
    return crud.listar_agendamentos_por_usuario(db, current_user.id)

@app.delete("/agendamentos/{agendamento_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancelar_agendamento_endpoint(
    agendamento_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_user_firebase)
):
    """
    Permite ao usuário cancelar um agendamento.
    """
    agendamento_cancelado = crud.cancelar_agendamento(db, agendamento_id, current_user.id)
    
    if agendamento_cancelado is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agendamento não encontrado ou você não tem permissão para cancelá-lo."
        )
    
    return JSONResponse(content={"message": "Agendamento cancelado com sucesso."}, status_code=status.HTTP_200_OK)

# --------- NOTIFICAÇÕES ---------

@app.get("/notificacoes/nao-lidas/contagem", response_model=schemas.NotificacaoContagemResponse)
def contar_notificacoes_nao_lidas_endpoint(
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_user_firebase)
):
    count = crud.contar_notificacoes_nao_lidas(db, current_user.id)
    return {"count": count}

@app.get("/notificacoes", response_model=List[schemas.NotificacaoResponse])
def listar_notificacoes_endpoint(
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_user_firebase)
):
    return crud.listar_notificacoes(db, current_user.id)

@app.post("/notificacoes/{id}/marcar-como-lida", status_code=status.HTTP_200_OK)
def marcar_notificacao_como_lida_endpoint(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_user_firebase)
):
    sucesso = crud.marcar_notificacao_como_lida(db, id, current_user.id)
    if not sucesso:
        raise HTTPException(status_code=404, detail="Notificação não encontrada ou não pertence ao usuário.")
    return {"message": "Notificação marcada como lida."}


# --------- FEED / POSTAGENS ---------

@app.post("/postagens", response_model=schemas.PostagemResponse)
async def criar_postagem(
    request_data: schemas.PostagemCreateRequest,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_user_firebase)
):
    barbeiro = crud.buscar_barbeiro_por_usuario_id(db, current_user.id)
    if not barbeiro:
        raise HTTPException(status_code=403, detail="Apenas barbeiros podem criar postagens")

    nova_postagem = crud.criar_postagem(
        db,
        request_data.postagem,
        barbeiro_id=barbeiro.id,
        foto_url_original=request_data.foto_urls.get("original"),
        foto_url_medium=request_data.foto_urls.get("medium"),
        foto_url_thumbnail=request_data.foto_urls.get("thumbnail")
    )
    return nova_postagem

@app.get("/feed", response_model=List[schemas.PostagemResponse])
def listar_feed(
    db: Session = Depends(get_db),
    limit: int = 10,
    offset: int = 0,
    current_user: Optional[models.Usuario] = Depends(get_current_user_firebase)
):
    usuario_id = current_user.id if current_user else None
    return crud.listar_feed(db, limit=limit, offset=offset, usuario_id_logado=usuario_id)

@app.delete("/postagens/{postagem_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_postagem_endpoint(
    postagem_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_user_firebase)
):
    barbeiro = crud.buscar_barbeiro_por_usuario_id(db, current_user.id)
    if not barbeiro:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Apenas barbeiros podem deletar postagens.")

    postagem_deletada = crud.deletar_postagem(db, postagem_id, barbeiro.id)

    if postagem_deletada is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Postagem não encontrada ou você não tem permissão para deletá-la.")

    return JSONResponse(content={"message": "Postagem deletada com sucesso."}, status_code=status.HTTP_200_OK)


# --------- CURTIDAS E COMENTÁRIOS ---------

@app.post("/postagens/{postagem_id}/curtir", status_code=status.HTTP_200_OK)
async def curtir_postagem(
    postagem_id: uuid.UUID, 
    db: Session = Depends(get_db), 
    current_user: models.Usuario = Depends(get_current_user_firebase)
):
    curtida_result = crud.toggle_curtida(db, current_user.id, postagem_id)
    
    postagem = crud.buscar_postagem_por_id(db, postagem_id)
    if not postagem:
        raise HTTPException(status_code=404, detail="Postagem não encontrada")
    
    if curtida_result: 
        barbeiro_usuario = postagem.barbeiro.usuario
        if barbeiro_usuario.id != current_user.id and barbeiro_usuario.fcm_tokens:
            mensagem_body = f"{current_user.nome} curtiu sua postagem: \"{postagem.titulo}\"."
            
            for token in list(barbeiro_usuario.fcm_tokens):
                try:
                    message = firebase_admin.messaging.Message(
                        token=token,
                        data={
                            "title": "Nova Curtida!",
                            "body": mensagem_body,
                            "tipo": "NOVA_CURTIDA", 
                            "post_id": str(postagem.id)
                        }
                    )
                    # CORREÇÃO AQUI
                    response = firebase_admin.Messaging(message)
                    logger.info(f"Notificação de curtida enviada para {token}. Response: {response}")
                except firebase_admin.messaging.FirebaseError as e:
                    logger.error(f"Erro ao enviar notificação de curtida para {token}: {e}")
                    crud.remover_fcm_token(db, barbeiro_usuario, token)

    return {"curtida": bool(curtida_result)}

@app.post("/comentarios", response_model=schemas.ComentarioResponse)
async def comentar(
    comentario: schemas.ComentarioCreate, 
    db: Session = Depends(get_db), 
    current_user: models.Usuario = Depends(get_current_user_firebase)
):
    novo_comentario = crud.criar_comentario(db, comentario, usuario_id=current_user.id)
    if not novo_comentario:
        raise HTTPException(status_code=404, detail="Postagem não encontrada para comentar.")

    postagem = crud.buscar_postagem_por_id(db, comentario.postagem_id)
    barbeiro_usuario = postagem.barbeiro.usuario

    if barbeiro_usuario.id != current_user.id and barbeiro_usuario.fcm_tokens:
        mensagem_body = f"{current_user.nome} comentou: \"{comentario.texto[:50]}...\""
        for token in list(barbeiro_usuario.fcm_tokens):
            try:
                message = firebase_admin.messaging.Message(
                    token=token,
                    data={
                        "title": "Novo Comentário!",
                        "body": mensagem_body,
                        "tipo": "NOVO_COMENTARIO", 
                        "post_id": str(postagem.id)
                    }
                )
                # CORREÇÃO AQUI
                response = firebase_admin.Messaging(message)
                logger.info(f"Notificação de comentário enviada para {token}. Response: {response}")
            except firebase_admin.messaging.FirebaseError as e:
                logger.error(f"Erro ao enviar notificação de comentário para {token}: {e}")
                crud.remover_fcm_token(db, barbeiro_usuario, token)

    return schemas.ComentarioResponse.model_validate(novo_comentario)


@app.get("/comentarios/{postagem_id}", response_model=List[schemas.ComentarioResponse])
def listar_comentarios(postagem_id: uuid.UUID, db: Session = Depends(get_db)):
    return crud.listar_comentarios(db, postagem_id)

@app.delete("/comentarios/{comentario_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_comentario_endpoint(
    comentario_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_user_firebase)
):
    comentario_deletado = crud.deletar_comentario(db, comentario_id, current_user.id)
    if comentario_deletado is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comentário não encontrado ou você não tem permissão para deletá-lo.")
    return JSONResponse(content={"message": "Comentário deletado com sucesso."}, status_code=status.HTTP_200_OK)


# --------- AVALIAÇÕES E PERFIS ---------

@app.post("/avaliacoes", response_model=schemas.AvaliacaoResponse)
def avaliar(avaliacao: schemas.AvaliacaoCreate, db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user_firebase)):
    return crud.criar_avaliacao(db, avaliacao, usuario_id=current_user.id)

@app.get("/avaliacoes/{barbeiro_id}", response_model=List[schemas.AvaliacaoResponse])
def listar_avaliacoes(barbeiro_id: uuid.UUID, db: Session = Depends(get_db)):
    return crud.listar_avaliacoes_barbeiro(db, barbeiro_id)

@app.get("/perfil_barbeiro/{barbeiro_id}", response_model=schemas.PerfilBarbeiroResponse)
def perfil_barbeiro(barbeiro_id: uuid.UUID, db: Session = Depends(get_db)):
    perfil = crud.obter_perfil_barbeiro(db, barbeiro_id)
    if not perfil or not perfil.get("barbeiro"):
        raise HTTPException(status_code=404, detail="Perfil do barbeiro não encontrado")
    return perfil


# --------- DADOS E AGENDA DO BARBEIRO LOGADO ---------

@app.get("/me/barbeiro", response_model=schemas.BarbeiroResponse)
def get_me_barbeiro(db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user_firebase)):
    barbeiro = crud.buscar_barbeiro_por_usuario_id(db, current_user.id)
    if not barbeiro:
        raise HTTPException(status_code=404, detail="Barbeiro não encontrado")
    return barbeiro

@app.put("/me/barbeiro", response_model=schemas.BarbeiroResponse)
def update_me_barbeiro(dados_update: schemas.BarbeiroUpdate, db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user_firebase)):
    barbeiro = crud.buscar_barbeiro_por_usuario_id(db, current_user.id)
    if not barbeiro:
        raise HTTPException(status_code=404, detail="Barbeiro não encontrado")
    return crud.atualizar_perfil_barbeiro(db, barbeiro, dados_update)

@app.put("/me/barbeiro/foto", response_model=schemas.BarbeiroResponse)
@app.post("/me/barbeiro/foto", response_model=schemas.BarbeiroResponse)
async def update_barbeiro_foto(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_user_firebase)
):
    barbeiro = crud.buscar_barbeiro_por_usuario_id(db, current_user.id)
    if not barbeiro:
        raise HTTPException(status_code=404, detail="Barbeiro não encontrado")

    if not CLOUD_STORAGE_BUCKET_NAME_GLOBAL:
        raise HTTPException(status_code=500, detail="Nome do bucket do Cloud Storage não configurado.")

    try:
        file_content = await file.read()
        filename_base = f"barbeiro_{barbeiro.id}-{os.path.splitext(file.filename)[0]}"
        
        uploaded_urls = await upload_and_resize_image(
            file_content=file_content,
            filename_base=filename_base,
            bucket_name=CLOUD_STORAGE_BUCKET_NAME_GLOBAL,
            content_type=file.content_type
        )
        return crud.atualizar_foto_barbeiro(
            db,
            barbeiro,
            foto_url_original=uploaded_urls.get("original"),
            foto_url_medium=uploaded_urls.get("medium"),
            foto_url_thumbnail=uploaded_urls.get("thumbnail")
        )
    except Exception as e:
        logger.error(f"ERRO CRÍTICO NO UPLOAD DE FOTO DE BARBEIRO: {e}")
        raise HTTPException(status_code=500, detail=f"Ocorreu um erro interno no servidor ao atualizar a foto: {e}")


@app.get("/me/agendamentos", response_model=List[schemas.AgendamentoResponse])
def listar_agendamentos_do_barbeiro(db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user_firebase)):
    barbeiro = crud.buscar_barbeiro_por_usuario_id(db, current_user.id)
    if not barbeiro:
        raise HTTPException(status_code=404, detail="Barbeiro não encontrado")
    return crud.listar_agendamentos_por_barbeiro(db, barbeiro.id)

@app.patch("/me/agendamentos/{agendamento_id}/cancelar", response_model=schemas.AgendamentoResponse)
async def cancelar_agendamento_pelo_barbeiro_endpoint(
    agendamento_id: uuid.UUID,
    request_data: schemas.AgendamentoCancelamentoRequest,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_user_firebase)
):
    barbeiro = crud.buscar_barbeiro_por_usuario_id(db, current_user.id)
    if not barbeiro:
        raise HTTPException(status_code=403, detail="Acesso negado. Apenas barbeiros podem cancelar agendamentos.")

    agendamento_cancelado = crud.cancelar_agendamento_pelo_barbeiro(
        db, 
        agendamento_id=agendamento_id, 
        barbeiro_id=barbeiro.id,
        motivo=request_data.motivo
    )

    if not agendamento_cancelado:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado ou não pertence a você.")

    cliente = crud.buscar_usuario_por_id(db, agendamento_cancelado.usuario_id)
    if cliente and cliente.fcm_tokens:
        mensagem_body = f"Seu agendamento com {barbeiro.usuario.nome} foi cancelado."
        if request_data.motivo:
            mensagem_body += f" Motivo: {request_data.motivo}"
        
        for token in list(cliente.fcm_tokens):
            try:
                message = firebase_admin.messaging.Message(
                    token=token,
                    data={
                        "title": "Agendamento Cancelado",
                        "body": mensagem_body,
                        "tipo": "AGENDAMENTO_CANCELADO", 
                        "agendamento_id": str(agendamento_cancelado.id)
                    }
                )
                # CORREÇÃO AQUI
                response = firebase_admin.Messaging(message)
                logger.info(f"Notificação de cancelamento enviada para {token}. Response: {response}")
            except firebase_admin.messaging.FirebaseError as e:
                logger.error(f"Erro ao enviar notificação de cancelamento para {token}: {e}")
                crud.remover_fcm_token(db, cliente, token)

    return agendamento_cancelado

@app.get("/me/horarios-trabalho", response_model=List[schemas.HorarioTrabalhoResponse])
def get_me_horarios_trabalho(db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user_firebase)):
    barbeiro = crud.buscar_barbeiro_por_usuario_id(db, current_user.id)
    if not barbeiro:
        raise HTTPException(status_code=403, detail="Apenas barbeiros podem consultar horários de trabalho.")
    return crud.listar_horarios_trabalho(db, barbeiro.id)


# FUNÇÃO AUXILIAR PARA UPLOAD E REDIMENSIONAMENTO
async def upload_and_resize_image(
    file_content: bytes,
    filename_base: str,
    bucket_name: str,
    content_type: str
) -> dict:
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    urls = {}
    extension = ".jpeg"
    if "png" in content_type:
        extension = ".png"
    elif "gif" in content_type:
        extension = ".gif"

    original_blob_name = f"uploads/{filename_base}_original{extension}"
    original_blob = bucket.blob(original_blob_name)
    original_blob.upload_from_string(file_content, content_type=content_type)
    urls['original'] = f"https://storage.googleapis.com/{bucket_name}/{original_blob_name}"

    image = Image.open(BytesIO(file_content))
    if image.mode == 'RGBA':
        image = image.convert('RGB')

    medium_size = (800, 800)
    image_medium = image.copy()
    image_medium.thumbnail(medium_size, Image.Resampling.LANCZOS)
    buffer_medium = BytesIO()
    image_medium.save(buffer_medium, format="JPEG", quality=85)
    buffer_medium.seek(0)
    medium_blob_name = f"uploads/{filename_base}_medium.jpeg"
    medium_blob = bucket.blob(medium_blob_name)
    medium_blob.upload_from_string(buffer_medium.getvalue(), content_type="image/jpeg")
    urls['medium'] = f"https://storage.googleapis.com/{bucket_name}/{medium_blob_name}"

    thumbnail_size = (200, 200)
    image_thumbnail = image.copy()
    image_thumbnail.thumbnail(thumbnail_size, Image.Resampling.LANCZOS)
    buffer_thumbnail = BytesIO()
    image_thumbnail.save(buffer_thumbnail, format="JPEG", quality=85)
    buffer_thumbnail.seek(0)
    thumbnail_blob_name = f"uploads/{filename_base}_thumbnail.jpeg"
    thumbnail_blob = bucket.blob(thumbnail_blob_name)
    thumbnail_blob.upload_from_string(buffer_thumbnail.getvalue(), content_type="image/jpeg")
    urls['thumbnail'] = f"https://storage.googleapis.com/{bucket_name}/{thumbnail_blob_name}"

    return urls

@app.post("/upload_foto")
async def upload_foto(file: UploadFile = File(...), current_user: models.Usuario = Depends(get_current_user_firebase)):
    if not CLOUD_STORAGE_BUCKET_NAME_GLOBAL:
        raise HTTPException(status_code=500, detail="Nome do bucket do Cloud Storage não configurado.")
    try:
        file_content = await file.read()
        filename_base = f"{uuid.uuid4()}-{os.path.splitext(file.filename)[0]}"
        uploaded_urls = await upload_and_resize_image(
            file_content=file_content,
            filename_base=filename_base,
            bucket_name=CLOUD_STORAGE_BUCKET_NAME_GLOBAL,
            content_type=file.content_type
        )
        return JSONResponse(content=uploaded_urls)
    except Exception as e:
        logger.error(f"ERRO CRÍTICO NO UPLOAD: {e}")
        raise HTTPException(status_code=500, detail=f"Ocorreu um erro interno no servidor: {e}")


# --------- DISPONIBILIDADE E HORÁRIOS ---------

@app.post("/me/horarios-trabalho", response_model=List[schemas.HorarioTrabalhoResponse])
def definir_horarios(horarios: List[schemas.HorarioTrabalhoCreate], db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user_firebase)):
    barbeiro = crud.buscar_barbeiro_por_usuario_id(db, current_user.id)
    if not barbeiro:
        raise HTTPException(status_code=403, detail="Apenas barbeiros podem definir horários.")
    return crud.definir_horarios_trabalho(db, barbeiro.id, horarios)

@app.post("/me/bloqueios", response_model=schemas.BloqueioResponse)
def criar_bloqueio(bloqueio: schemas.BloqueioCreate, db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user_firebase)):
    barbeiro = crud.buscar_barbeiro_por_usuario_id(db, current_user.id)
    if not barbeiro:
        raise HTTPException(status_code=403, detail="Apenas barbeiros podem criar bloqueios.")
    return crud.criar_bloqueio(db, barbeiro.id, bloqueio)

@app.delete("/me/bloqueios/{bloqueio_id}", status_code=204)
def deletar_bloqueio(bloqueio_id: uuid.UUID, db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user_firebase)):
    barbeiro = crud.buscar_barbeiro_por_usuario_id(db, current_user.id)
    if not barbeiro:
        raise HTTPException(status_code=403, detail="Acesso negado.")
    if not crud.deletar_bloqueio(db, bloqueio_id, barbeiro.id):
        raise HTTPException(status_code=404, detail="Bloqueio não encontrado.")
    return

@app.get("/barbeiros/{barbeiro_id}/horarios-disponiveis", response_model=List[time])
def get_horarios_disponiveis(barbeiro_id: uuid.UUID, dia: date, db: Session = Depends(get_db)):
    return crud.calcular_horarios_disponiveis(db, barbeiro_id, dia)


# --------- ENDPOINT DE TESTE PARA NOTIFICAÇÕES FCM ---------

class FCMTestRequest(BaseModel):
    token: str

@app.post("/test-fcm")
async def test_fcm_notification(request: FCMTestRequest):
    """
    Endpoint temporário para depurar o envio de notificações FCM.
    Envia uma mensagem data-only para um token específico e loga a resposta da API do Google.
    """
    logger.info(f"Iniciando teste de notificação para o token: {request.token}")

    message = firebase_admin.messaging.Message(
        token=request.token,
        data={
            "title": "Teste do Backend",
            "body": "Esta é uma mensagem de teste enviada diretamente pelo servidor.",
            "tipo": "TESTE_BACKEND",
            "timestamp": str(datetime.utcnow())
        }
    )

    try:
        # Tenta enviar a mensagem
        response = firebase_admin.Messaging(message)
        
        # Se funcionar, a API do Google retorna um ID de mensagem. VAMOS LOGAR ISSO.
        success_log = f"SUCESSO! Notificação enviada. Resposta da API do Google: {response}"
        print(success_log)
        logger.info(success_log)
        
        return {"status": "sucesso", "response_from_google": response}

    except Exception as e:
        # Se falhar, a API do Google retorna um erro. VAMOS LOGAR O ERRO.
        error_log = f"ERRO! Falha ao enviar notificação. Detalhes da exceção: {e}"
        print(error_log)
        logger.error(error_log)
        
        # Retorna o erro como resposta para facilitar a depuração
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

# ----------------------------------------------------------------

# ... (resto do seu código, como a seção de SERVIÇOS) ...


# --------- SERVIÇOS ---------

@app.post("/me/servicos", response_model=schemas.ServicoResponse)
def criar_servico(servico: schemas.ServicoCreate, db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user_firebase)):
    barbeiro = crud.buscar_barbeiro_por_usuario_id(db, current_user.id)
    if not barbeiro:
        raise HTTPException(status_code=403, detail="Apenas barbeiros podem criar serviços.")
    return crud.criar_servico(db, servico, barbeiro.id)

@app.get("/me/servicos", response_model=List[schemas.ServicoResponse])
def listar_meus_servicos(db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user_firebase)):
    barbeiro = crud.buscar_barbeiro_por_usuario_id(db, current_user.id)
    if not barbeiro:
        raise HTTPException(status_code=404, detail="Barbeiro não encontrado")
    return crud.listar_servicos_por_barbeiro(db, barbeiro.id)

@app.get("/barbeiros/{barbeiro_id}/servicos", response_model=List[schemas.ServicoResponse])
def listar_servicos(barbeiro_id: uuid.UUID, db: Session = Depends(get_db)):
    return crud.listar_servicos_por_barbeiro(db, barbeiro_id)

@app.put("/me/servicos/{servico_id}", response_model=schemas.ServicoResponse)
def atualizar_servico_endpoint(
    servico_id: uuid.UUID,
    servico_update: schemas.ServicoUpdate,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_user_firebase)
):
    barbeiro = crud.buscar_barbeiro_por_usuario_id(db, current_user.id)
    if not barbeiro:
        raise HTTPException(status_code=403, detail="Apenas barbeiros podem atualizar serviços.")

    servico_atualizado = crud.atualizar_servico(db, servico_id, servico_update, barbeiro.id)
    if not servico_atualizado:
        raise HTTPException(status_code=404, detail="Serviço não encontrado ou você não tem permissão para atualizá-lo.")

    return servico_atualizado

@app.delete("/me/servicos/{servico_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_servico_endpoint(
    servico_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_user_firebase)
):
    barbeiro = crud.buscar_barbeiro_por_usuario_id(db, current_user.id)
    if not barbeiro:
        raise HTTPException(status_code=403, detail="Apenas barbeiros podem deletar serviços.")

    if not crud.deletar_servico(db, servico_id, barbeiro.id):
        raise HTTPException(status_code=404, detail="Serviço não encontrado ou você não tem permissão para deletá-lo.")
    return