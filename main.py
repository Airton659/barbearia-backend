# barbearia-backend/main.py
import asyncio
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
from datetime import date, time, timedelta, datetime, timezone
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
from firebase_admin import messaging
from firebase_admin import exceptions as fb_exceptions

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
    usuario_existente = crud.buscar_usuario_por_email(db, email=usuario.email)
    if usuario_existente:
        raise HTTPException(status_code=400, detail="Email já cadastrado")
    novo_usuario = crud.criar_usuario(db=db, usuario=usuario)
    return novo_usuario

@app.get("/usuarios/{usuario_id}", response_model=schemas.UsuarioResponse)
def obter_usuario(usuario_id: uuid.UUID, db: Session = Depends(get_db)):
    usuario = crud.buscar_usuario(db, usuario_id)
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return usuario

@app.put("/usuarios/{usuario_id}", response_model=schemas.UsuarioResponse)
def atualizar_usuario(usuario_id: uuid.UUID, usuario: schemas.UsuarioUpdate, db: Session = Depends(get_db)):
    usuario_atualizado = crud.atualizar_usuario(db, usuario_id, usuario)
    if not usuario_atualizado:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return usuario_atualizado

@app.delete("/usuarios/{usuario_id}")
def deletar_usuario(usuario_id: uuid.UUID, db: Session = Depends(get_db)):
    if not crud.deletar_usuario(db, usuario_id):
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return {"mensagem": "Usuário deletado com sucesso"}

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
        return {"mensagem": "Se o e-mail existir, enviaremos instruções de recuperação."}

    # Aqui você implementaria o envio de e-mail de recuperação
    # Por enquanto, apenas retornamos uma resposta simples
    return {"mensagem": "Instruções de recuperação enviadas para seu e-mail."}


# --------- BARBEIROS ---------

@app.post("/barbeiros", response_model=schemas.BarbeiroResponse)
def criar_barbeiro(barbeiro: schemas.BarbeiroCreate, db: Session = Depends(get_db)):
    usuario = crud.buscar_usuario(db, barbeiro.usuario_id)
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    novo_barbeiro = crud.criar_barbeiro(db, barbeiro)
    return novo_barbeiro

@app.get("/barbeiros", response_model=List[schemas.BarbeiroResponse])
def listar_barbeiros(db: Session = Depends(get_db), local_kw: Optional[str] = None):
    return crud.listar_barbeiros(db, local_kw=local_kw)

@app.get("/barbeiros/{barbeiro_id}", response_model=schemas.BarbeiroResponse)
def obter_barbeiro(barbeiro_id: uuid.UUID, db: Session = Depends(get_db)):
    barbeiro = crud.buscar_barbeiro(db, barbeiro_id)
    if not barbeiro:
        raise HTTPException(status_code=404, detail="Barbeiro não encontrado")
    return barbeiro

@app.put("/barbeiros/{barbeiro_id}", response_model=schemas.BarbeiroResponse)
def atualizar_barbeiro(barbeiro_id: uuid.UUID, barbeiro: schemas.BarbeiroUpdate, db: Session = Depends(get_db)):
    barbeiro_atualizado = crud.atualizar_barbeiro(db, barbeiro_id, barbeiro)
    if not barbeiro_atualizado:
        raise HTTPException(status_code=404, detail="Barbeiro não encontrado")
    return barbeiro_atualizado

@app.delete("/barbeiros/{barbeiro_id}")
def deletar_barbeiro(barbeiro_id: uuid.UUID, db: Session = Depends(get_db)):
    if not crud.deletar_barbeiro(db, barbeiro_id):
        raise HTTPException(status_code=404, detail="Barbeiro não encontrado")
    return {"mensagem": "Barbeiro deletado com sucesso"}


# --------- SERVIÇOS ---------

@app.post("/servicos", response_model=schemas.ServicoResponse)
def criar_servico(servico: schemas.ServicoCreate, db: Session = Depends(get_db)):
    barbeiro = crud.buscar_barbeiro(db, servico.barbeiro_id)
    if not barbeiro:
        raise HTTPException(status_code=404, detail="Barbeiro não encontrado")
    novo_servico = crud.criar_servico(db, servico)
    return novo_servico

@app.get("/servicos", response_model=List[schemas.ServicoResponse])
def listar_servicos(db: Session = Depends(get_db)):
    return crud.listar_servicos(db)

@app.get("/servicos/{servico_id}", response_model=schemas.ServicoResponse)
def obter_servico(servico_id: uuid.UUID, db: Session = Depends(get_db)):
    servico = crud.buscar_servico(db, servico_id)
    if not servico:
        raise HTTPException(status_code=404, detail="Serviço não encontrado")
    return servico

@app.put("/servicos/{servico_id}", response_model=schemas.ServicoResponse)
def atualizar_servico(servico_id: uuid.UUID, servico: schemas.ServicoUpdate, db: Session = Depends(get_db)):
    servico_atualizado = crud.atualizar_servico(db, servico_id, servico)
    if not servico_atualizado:
        raise HTTPException(status_code=404, detail="Serviço não encontrado")
    return servico_atualizado

@app.delete("/servicos/{servico_id}")
def deletar_servico(servico_id: uuid.UUID, db: Session = Depends(get_db)):
    if not crud.deletar_servico(db, servico_id):
        raise HTTPException(status_code=404, detail="Serviço não encontrado")
    return {"mensagem": "Serviço deletado com sucesso"}


# --------- POSTAGENS (FEED) ---------

@app.post("/postagens", response_model=schemas.PostagemResponse)
def criar_postagem(postagem: schemas.PostagemCreate, db: Session = Depends(get_db)):
    barbeiro = crud.buscar_barbeiro(db, postagem.barbeiro_id)
    if not barbeiro:
        raise HTTPException(status_code=404, detail="Barbeiro não encontrado")
    nova_postagem = crud.criar_postagem(db, postagem)
    return nova_postagem

@app.get("/postagens", response_model=List[schemas.PostagemResponse])
def listar_postagens(db: Session = Depends(get_db)):
    return crud.listar_postagens(db)

@app.get("/postagens/{postagem_id}", response_model=schemas.PostagemResponse)
def obter_postagem(postagem_id: uuid.UUID, db: Session = Depends(get_db)):
    postagem = crud.buscar_postagem(db, postagem_id)
    if not postagem:
        raise HTTPException(status_code=404, detail="Postagem não encontrada")
    return postagem

@app.delete("/postagens/{postagem_id}")
def deletar_postagem(postagem_id: uuid.UUID, db: Session = Depends(get_db)):
    if not crud.deletar_postagem(db, postagem_id):
        raise HTTPException(status_code=404, detail="Postagem não encontrada")
    return {"mensagem": "Postagem deletada com sucesso"}


# --------- AGENDAMENTOS ---------

@app.post("/agendamentos", response_model=schemas.AgendamentoResponse)
async def agendar(agendamento: schemas.AgendamentoCreate, db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user_firebase)):
    barbeiro = crud.buscar_barbeiro(db, agendamento.barbeiro_id)
    if not barbeiro:
        raise HTTPException(status_code=404, detail="Barbeiro não encontrado")

    novo_agendamento = crud.criar_agendamento(db, agendamento, current_user.id)

    # Notificação para o barbeiro
    if barbeiro.usuario and barbeiro.usuario.fcm_tokens:
        mensagem_body = f"Você tem um novo agendamento de {current_user.nome} para o dia {novo_agendamento.data_agendada.strftime('%d/%m/%Y')} às {novo_agendamento.hora_agendada.strftime('%H:%M')}."
        
        tokens_a_enviar = list(barbeiro.usuario.fcm_tokens)
        
        for token in tokens_a_enviar:
            try:
                message = messaging.Message(
                    token=token,
                    data={
                        "title": "Novo Agendamento!",
                        "body": mensagem_body,
                        "tipo": "NOVO_AGENDAMENTO",
                        "agendamento_id": str(novo_agendamento.id)
                    }
                )
                
                # CORREÇÃO AQUI
                loop = asyncio.get_running_loop()
                response = await loop.run_in_executor(None, messaging.send, message)
                logger.info(f"Notificação push enviada para o token: {token}. Response: {response}")

            except fb_exceptions.FirebaseError as e:
                logger.error(f"Erro ao enviar notificação para o token {token}: {e}")
                if e.code in ['invalid-argument', 'unregistered', 'sender-id-mismatch']:
                    crud.remover_fcm_token(db, barbeiro.usuario, token)
            except Exception as e:
                logger.error(f"Erro inesperado ao enviar notificação: {e}")

    return novo_agendamento

@app.get("/agendamentos", response_model=List[schemas.AgendamentoResponse])
def listar_agendamentos(db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user_firebase)):
    return crud.listar_agendamentos_por_usuario(db, current_user.id)

@app.get("/agendamentos/{agendamento_id}", response_model=schemas.AgendamentoResponse)
def obter_agendamento(agendamento_id: uuid.UUID, db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user_firebase)):
    agendamento = crud.buscar_agendamento_por_id_e_usuario(db, agendamento_id, current_user.id)
    if not agendamento:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado")
    return agendamento

@app.delete("/agendamentos/{agendamento_id}")
def deletar_agendamento(agendamento_id: uuid.UUID, db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user_firebase)):
    if not crud.deletar_agendamento(db, agendamento_id, current_user.id):
        raise HTTPException(status_code=404, detail="Agendamento não encontrado ou você não tem permissão para deletá-lo")
    return {"mensagem": "Agendamento deletado com sucesso"}


# --------- CURTIDAS ---------

@app.post("/postagens/{postagem_id}/curtir")
async def curtir_postagem(postagem_id: uuid.UUID, db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user_firebase)):
    postagem = crud.buscar_postagem(db, postagem_id)
    if not postagem:
        raise HTTPException(status_code=404, detail="Postagem não encontrada")

    curtida_result = crud.curtir_postagem(db, postagem_id, current_user.id)

    # Notificar o barbeiro dono da postagem
    barbeiro_usuario = crud.buscar_usuario_por_id(db, postagem.usuario_id)
    if barbeiro_usuario and barbeiro_usuario.fcm_tokens:
        mensagem_body = f"{current_user.nome} curtiu sua postagem: \"{postagem.titulo}\"."
        
        for token in list(barbeiro_usuario.fcm_tokens):
            try:
                message = messaging.Message(
                    token=token,
                    data={
                        "title": "Nova Curtida!",
                        "body": mensagem_body,
                        "tipo": "NOVA_CURTIDA", 
                        "post_id": str(postagem.id)
                    }
                )
                # CORREÇÃO AQUI
                loop = asyncio.get_running_loop()
                response = await loop.run_in_executor(None, messaging.send, message)
                logger.info(f"Notificação de curtida enviada para {token}. Response: {response}")
            except fb_exceptions.FirebaseError as e:
                logger.error(f"Erro ao enviar notificação de curtida para {token}: {e}")
                crud.remover_fcm_token(db, barbeiro_usuario, token)
            except Exception as e:
                logger.error(f"Erro inesperado ao enviar notificação de curtida: {e}")

    return {"curtida": bool(curtida_result)}

@app.post("/comentarios", response_model=schemas.ComentarioResponse)
async def comentar(
    comentario: schemas.ComentarioCreate, 
    db: Session = Depends(get_db), 
    current_user: models.Usuario = Depends(get_current_user_firebase)
):
    postagem = crud.buscar_postagem(db, comentario.postagem_id)
    if not postagem:
        raise HTTPException(status_code=404, detail="Postagem não encontrada")

    novo_comentario = crud.criar_comentario(db, comentario, current_user.id)

    # Notificar o barbeiro dono da postagem
    barbeiro_usuario = crud.buscar_usuario_por_id(db, postagem.usuario_id)
    if barbeiro_usuario and barbeiro_usuario.fcm_tokens:
        mensagem_body = f"{current_user.nome} comentou: \"{comentario.texto[:50]}...\""
        for token in list(barbeiro_usuario.fcm_tokens):
            try:
                message = messaging.Message(
                    token=token,
                    data={
                        "title": "Novo Comentário!",
                        "body": mensagem_body,
                        "tipo": "NOVO_COMENTARIO", 
                        "post_id": str(postagem.id)
                    }
                )
                # CORREÇÃO AQUI
                loop = asyncio.get_running_loop()
                response = await loop.run_in_executor(None, messaging.send, message)
                logger.info(f"Notificação de comentário enviada para {token}. Response: {response}")
            except fb_exceptions.FirebaseError as e:
                logger.error(f"Erro ao enviar notificação de comentário para {token}: {e}")
                crud.remover_fcm_token(db, barbeiro_usuario, token)
            except Exception as e:
                logger.error(f"Erro inesperado ao enviar notificação de comentário: {e}")

    return novo_comentario


# --------- FOTOS / IMAGENS (GCS) ---------

def _get_bucket_or_500():
    bucket_name = CLOUD_STORAGE_BUCKET_NAME_GLOBAL
    if not bucket_name:
        raise HTTPException(status_code=500, detail="Nome do bucket do Cloud Storage não configurado (CLOUD_STORAGE_BUCKET_NAME).")
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    return bucket, bucket_name

def _upload_image_and_thumbs(image_bytes: bytes, folder: str, filename_base: str, content_type="image/jpeg"):
    bucket, bucket_name = _get_bucket_or_500()

    # Salva original
    original_blob_name = f"{folder}/{filename_base}.jpg"
    original_blob = bucket.blob(original_blob_name)
    original_blob.upload_from_string(image_bytes, content_type=content_type)
    original_url = f"https://storage.googleapis.com/{bucket_name}/{original_blob_name}"

    # Gera e salva miniatura
    image = Image.open(BytesIO(image_bytes))
    image.thumbnail((300, 300))
    thumb_io = BytesIO()
    image.save(thumb_io, format="JPEG")
    thumb_io.seek(0)

    thumbnail_blob_name = f"{folder}/{filename_base}_thumb.jpg"
    thumbnail_blob = bucket.blob(thumbnail_blob_name)
    thumbnail_blob.upload_from_string(thumb_io.read(), content_type="image/jpeg")
    thumb_url = f"https://storage.googleapis.com/{bucket_name}/{thumbnail_blob_name}"

    return {"original": original_url, "thumbnail": thumb_url}

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

    file_bytes = await file.read()
    filename_base = f"barbeiros/{barbeiro.id}/perfil_{int(time.time())}"
    urls = _upload_image_and_thumbs(file_bytes, "barbeiros", f"{barbeiro.id}/perfil_{int(time.time())}")

    # Atualiza foto do barbeiro
    barbeiro.foto_url = urls["original"]
    barbeiro.foto_url_thumbnail = urls["thumbnail"]
    db.commit()
    db.refresh(barbeiro)

    return barbeiro

@app.post("/upload_foto_galeria", response_model=schemas.GaleriaFotoResponse)
async def upload_foto_galeria(
    file: UploadFile = UploadFile,
    barbeiro_id: uuid.UUID = None,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_user_firebase)
):
    if not barbeiro_id:
        raise HTTPException(status_code=400, detail="barbeiro_id é obrigatório")

    barbeiro = crud.buscar_barbeiro(db, barbeiro_id)
    if not barbeiro:
        raise HTTPException(status_code=404, detail="Barbeiro não encontrado")

    # Apenas o barbeiro logado pode enviar para sua galeria
    meu_barbeiro = crud.buscar_barbeiro_por_usuario_id(db, current_user.id)
    if not meu_barbeiro or meu_barbeiro.id != barbeiro_id:
        raise HTTPException(status_code=403, detail="Você não tem permissão para enviar fotos para a galeria deste barbeiro")

    file_bytes = await file.read()
    filename_base = f"barbeiros/{barbeiro_id}/galeria_{int(time.time())}"
    urls = _upload_image_and_thumbs(file_bytes, "barbeiros", f"{barbeiro_id}/galeria_{int(time.time())}")

    foto = crud.adicionar_foto_galeria(db, barbeiro_id, urls["original"], urls["thumbnail"])
    return foto

@app.get("/barbeiros/{barbeiro_id}/galeria", response_model=List[schemas.GaleriaFotoResponse])
def listar_galeria(barbeiro_id: uuid.UUID, db: Session = Depends(get_db)):
    return crud.listar_fotos_galeria(db, barbeiro_id)

@app.delete("/galeria/{foto_id}")
def deletar_foto_galeria(foto_id: uuid.UUID, db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user_firebase)):
    foto = crud.buscar_foto_galeria(db, foto_id)
    if not foto:
        raise HTTPException(status_code=404, detail="Foto não encontrada")

    barbeiro = crud.buscar_barbeiro_por_usuario_id(db, current_user.id)
    if not barbeiro or barbeiro.id != foto.barbeiro_id:
        raise HTTPException(status_code=403, detail="Você não tem permissão para deletar esta foto")

    if not crud.deletar_foto_galeria(db, foto_id):
        raise HTTPException(status_code=404, detail="Foto não encontrada")
    return {"mensagem": "Foto deletada com sucesso"}


# --------- UPLOAD GENÉRICO (LEGADO) ---------

def save_upload_to_gcs(file_bytes: bytes, destination_blob_name: str, content_type="image/jpeg"):
    bucket, bucket_name = _get_bucket_or_500()
    blob = bucket.blob(destination_blob_name)
    blob.upload_from_string(file_bytes, content_type=content_type)
    return f"https://storage.googleapis.com/{bucket_name}/{destination_blob_name}"

def generate_thumbnails(image_bytes: bytes, sizes=[(300, 300)]):
    urls = {}
    bucket, bucket_name = _get_bucket_or_500()

    # Salvar original
    original_blob_name = f"uploads/{uuid.uuid4()}.jpg"
    original_blob = bucket.blob(original_blob_name)
    original_blob.upload_from_string(image_bytes, content_type="image/jpeg")
    urls['original'] = f"https://storage.googleapis.com/{bucket_name}/{original_blob_name}"

    # Thumbs
    image = Image.open(BytesIO(image_bytes))
    for size in sizes:
        img_copy = image.copy()
        img_copy.thumbnail(size)
        thumb_io = BytesIO()
        img_copy.save(thumb_io, format="JPEG")
        thumb_io.seek(0)
        thumbnail_blob_name = f"uploads/thumb_{size[0]}x{size[1]}_{uuid.uuid4()}.jpg"
        thumbnail_blob = bucket.blob(thumbnail_blob_name)
        thumbnail_blob.upload_from_string(thumb_io.read(), content_type="image/jpeg")
        urls[f"thumb_{size[0]}x{size[1]}"] = f"https://storage.googleapis.com/{bucket_name}/{thumbnail_blob_name}"

    return urls

@app.post("/upload_foto")
async def upload_foto(file: UploadFile = File(...), current_user: models.Usuario = Depends(get_current_user_firebase)):
    if not CLOUD_STORAGE_BUCKET_NAME_GLOBAL:
        raise HTTPException(status_code=500, detail="Nome do bucket do Cloud Storage não configurado (CLOUD_STORAGE_BUCKET_NAME).")

    file_bytes = await file.read()
    urls = generate_thumbnails(file_bytes, sizes=[(300, 300)])
    return urls


# --------- CANCELAMENTO DE AGENDAMENTO (pelo barbeiro) ---------

class CancelamentoRequest(BaseModel):
    motivo: Optional[str] = None

@app.patch("/me/agendamentos/{agendamento_id}/cancelar", response_model=schemas.AgendamentoResponse)
async def cancelar_agendamento_pelo_barbeiro_endpoint(
    agendamento_id: uuid.UUID,
    request_data: CancelamentoRequest,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_user_firebase)
):
    barbeiro = crud.buscar_barbeiro_por_usuario_id(db, current_user.id)
    if not barbeiro:
        raise HTTPException(status_code=403, detail="Apenas barbeiros podem cancelar agendamentos.")

    agendamento_cancelado = crud.cancelar_agendamento_pelo_barbeiro(db, agendamento_id, barbeiro.id)
    if not agendamento_cancelado:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado ou não pertence a você.")

    # Notificar o cliente
    cliente = crud.buscar_usuario_por_id(db, agendamento_cancelado.usuario_id)
    if cliente and cliente.fcm_tokens:
        mensagem_body = f"Seu agendamento em {agendamento_cancelado.data_agendada.strftime('%d/%m/%Y')} às {agendamento_cancelado.hora_agendada.strftime('%H:%M')} foi cancelado."
        if request_data.motivo:
            mensagem_body += f" Motivo: {request_data.motivo}"
        
        for token in list(cliente.fcm_tokens):
            try:
                message = messaging.Message(
                    token=token,
                    data={
                        "title": "Agendamento Cancelado",
                        "body": mensagem_body,
                        "tipo": "AGENDAMENTO_CANCELADO", 
                        "agendamento_id": str(agendamento_cancelado.id)
                    }
                )
                # CORREÇÃO AQUI
                loop = asyncio.get_running_loop()
                response = await loop.run_in_executor(None, messaging.send, message)
                logger.info(f"Notificação de cancelamento enviada para {token}. Response: {response}")
            except fb_exceptions.FirebaseError as e:
                logger.error(f"Erro ao enviar notificação de cancelamento para {token}: {e}")
                crud.remover_fcm_token(db, cliente, token)
            except Exception as e:
                logger.error(f"Erro inesperado ao enviar notificação de cancelamento: {e}")

    return agendamento_cancelado


# --------- HORÁRIOS DISPONÍVEIS ---------

@app.get("/barbeiros/{barbeiro_id}/horarios-disponiveis", response_model=List[schemas.HorarioDisponivel])
def horarios_disponiveis_endpoint(barbeiro_id: uuid.UUID, dia: date, db: Session = Depends(get_db)):
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

    # Mensagem DATA-ONLY (não incluir 'notification')
    message = messaging.Message(
        token=request.token,
        data={
            "title": "Teste do Backend",
            "body": "Esta é uma mensagem de teste enviada diretamente pelo servidor.",
            "tipo": "TESTE_BACKEND",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    )

    try:
        # Envia sem bloquear o event loop (messaging.send é síncrono)
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(None, messaging.send, message)

        success_log = f"SUCESSO! Notificação enviada. message_id: {response}"
        print(success_log)
        logger.info(success_log)

        return {"status": "sucesso", "message_id": response}

    except Exception as e:
        error_log = f"ERRO! Falha ao enviar notificação. Detalhes: {e}"
        print(error_log)
        logger.error(error_log)

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# --------- MEUS SERVIÇOS (barbeiro logado) ---------

@app.get("/me/servicos", response_model=List[schemas.ServicoResponse])
def listar_servicos_endpoint(
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_user_firebase)
):
    barbeiro = crud.buscar_barbeiro_por_usuario_id(db, current_user.id)
    if not barbeiro:
        raise HTTPException(status_code=403, detail="Apenas barbeiros podem listar seus serviços.")
    return crud.listar_servicos_por_barbeiro(db, barbeiro.id)

@app.post("/me/servicos", response_model=schemas.ServicoResponse)
def criar_servico_endpoint(
    servico: schemas.ServicoCreate,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_user_firebase)
):
    barbeiro = crud.buscar_barbeiro_por_usuario_id(db, current_user.id)
    if not barbeiro:
        raise HTTPException(status_code=403, detail="Apenas barbeiros podem criar serviços.")
    return crud.criar_servico(db, servico)

@app.put("/me/servicos/{servico_id}", response_model=schemas.ServicoResponse)
def atualizar_servico_endpoint(
    servico_id: uuid.UUID,
    servico: schemas.ServicoUpdate,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_user_firebase)
):
    barbeiro = crud.buscar_barbeiro_por_usuario_id(db, current_user.id)
    if not barbeiro:
        raise HTTPException(status_code=403, detail="Apenas barbeiros podem atualizar serviços.")
    servico_atualizado = crud.atualizar_servico(db, servico_id, servico, barbeiro.id)
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
