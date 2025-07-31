# barbearia-backend/main.py

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session, joinedload # Adicionado joinedload para buscar barbeiro
from sqlalchemy.exc import OperationalError
from typing import List, Optional
import models, schemas, crud
import uuid
import time
import os
from datetime import date, time, timedelta
from auth import criar_token, get_current_user, get_current_admin_user
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse
import httpx
from database import get_db, engine
from google.cloud import storage 
from PIL import Image
from io import BytesIO

app = FastAPI()

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

@app.post("/login", response_model=schemas.TokenResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    usuario = crud.buscar_usuario_por_email(db, form_data.username)
    if not usuario or not usuario.verificar_senha(form_data.password):
        raise HTTPException(status_code=401, detail="Credenciais inválidas")
    
    token_data = {"sub": str(usuario.id), "tipo": usuario.tipo}
    
    # ALTERAÇÃO AQUI: Adiciona barbeiro_id ao token_data se o usuário for um barbeiro
    if usuario.tipo == "barbeiro":
        barbeiro = crud.buscar_barbeiro_por_usuario_id(db, usuario.id)
        if barbeiro: # Verifica se o objeto barbeiro realmente existe
            token_data["barbeiro_id"] = str(barbeiro.id)

    token = criar_token(token_data)
    return {"access_token": token, "token_type": "bearer"}


# --------- USUÁRIOS ---------

@app.post("/usuarios", response_model=schemas.UsuarioResponse)
def criar_usuario(usuario: schemas.UsuarioCreate, db: Session = Depends(get_db)):
    existente = crud.buscar_usuario_por_email(db, usuario.email)
    if existente:
        raise HTTPException(status_code=400, detail="Email já cadastrado")
    return crud.criar_usuario(db, usuario)

@app.get("/me", response_model=schemas.UsuarioResponse)
def get_me(current_user: models.Usuario = Depends(get_current_user)):
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


# --------- ADMIN ---------

@app.get("/admin/usuarios", response_model=List[schemas.UsuarioResponse])
def admin_listar_usuarios(db: Session = Depends(get_db), admin: models.Usuario = Depends(get_current_admin_user)):
    return crud.listar_todos_usuarios(db)

@app.put("/admin/usuarios/{usuario_id}/promover", response_model=schemas.BarbeiroResponse)
def admin_promover_para_barbeiro(
    usuario_id: uuid.UUID,
    info_barbeiro: schemas.BarbeiroPromote, 
    db: Session = Depends(get_db), 
    admin: models.Usuario = Depends(get_current_admin_user)
):
    barbeiro_criado = crud.promover_usuario_para_barbeiro(db, usuario_id, info_barbeiro)
    if not barbeiro_criado:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    return barbeiro_criado


# --------- BARBEIROS ---------

@app.get("/barbeiros", response_model=List[schemas.BarbeiroResponse])
def listar_barbeiros(db: Session = Depends(get_db), especialidade: Optional[str] = None):
    return crud.listar_barbeiros(db, especialidade=especialidade)


# --------- AGENDAMENTOS ---------

@app.post("/agendamentos", response_model=schemas.AgendamentoResponse)
def agendar(agendamento: schemas.AgendamentoCreate, db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user)):
    return crud.criar_agendamento(db, agendamento, usuario_id=current_user.id)

@app.get("/agendamentos", response_model=List[schemas.AgendamentoResponse])
def listar_agendamentos(db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user)):
    return crud.listar_agendamentos_por_usuario(db, current_user.id)

@app.delete("/agendamentos/{agendamento_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancelar_agendamento_endpoint(
    agendamento_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_user)
):
    """
    Permite ao usuário cancelar um agendamento.
    """
    agendamento_cancelado = crud.cancelar_agendamento(db, agendamento_id, current_user.id)
    
    if agendamento_cancelado is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agendamento não encontrado ou você não tem permissão para cancelá-lo.")
    
    return {"message": "Agendamento cancelado com sucesso."}


# --------- FEED / POSTAGENS ---------

@app.post("/postagens", response_model=schemas.PostagemResponse)
async def criar_postagem(
    request_data: schemas.PostagemCreateRequest,
    db: Session = Depends(get_db), 
    current_user: models.Usuario = Depends(get_current_user)
):
    barbeiro = crud.buscar_barbeiro_por_usuario_id(db, current_user.id)
    if not barbeiro:
        raise HTTPException(status_code=403, detail="Apenas barbeiros podem criar postagens")

    return crud.criar_postagem(
        db, 
        request_data.postagem,
        barbeiro_id=barbeiro.id,
        foto_url_original=request_data.foto_urls.get("original"),
        foto_url_medium=request_data.foto_urls.get("medium"),
        foto_url_thumbnail=request_data.foto_urls.get("thumbnail")
    )

@app.get("/feed", response_model=List[schemas.PostagemResponse])
def listar_feed(
    db: Session = Depends(get_db), 
    limit: int = 10, 
    offset: int = 0,
    current_user: Optional[models.Usuario] = Depends(get_current_user) # Torna o usuário atual opcional
):
    # A lógica para verificar a curtida será adicionada no crud.py
    return crud.listar_feed(db, limit=limit, offset=offset, usuario_id_logado=current_user.id if current_user else None)


@app.delete("/postagens/{postagem_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_postagem_endpoint(
    postagem_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_user)
):
    """
    Permite ao barbeiro logado excluir uma postagem que ele mesmo criou.
    """
    barbeiro = crud.buscar_barbeiro_por_usuario_id(db, current_user.id)
    if not barbeiro:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Apenas barbeiros podem deletar postagens.")

    postagem_deletada = crud.deletar_postagem(db, postagem_id, barbeiro.id)
    
    if postagem_deletada is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Postagem não encontrada ou você não tem permissão para deletá-la.")
    
    return {"message": "Postagem deletada com sucesso."}


# --------- CURTIDAS E COMENTÁRIOS ---------

@app.post("/postagens/{postagem_id}/curtir")
def curtir_postagem(postagem_id: uuid.UUID, db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user)):
    resultado = crud.toggle_curtida(db, current_user.id, postagem_id)
    if resultado is None and crud.buscar_postagem_por_id(db, postagem_id) is None:
        raise HTTPException(status_code=404, detail="Postagem não encontrada")
    return {"curtida": bool(resultado)}

@app.post("/comentarios", response_model=schemas.ComentarioResponse)
def comentar(comentario: schemas.ComentarioCreate, db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user)):
    return crud.criar_comentario(db, comentario, usuario_id=current_user.id)

@app.get("/comentarios/{postagem_id}", response_model=List[schemas.ComentarioResponse])
def listar_comentarios(postagem_id: uuid.UUID, db: Session = Depends(get_db)):
    return crud.listar_comentarios(db, postagem_id)

@app.delete("/comentarios/{comentario_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_comentario_endpoint(
    comentario_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_user)
):
    """
    Permite ao usuário logado excluir um comentário que ele mesmo fez.
    """
    comentario_deletado = crud.deletar_comentario(db, comentario_id, current_user.id)
    
    if comentario_deletado is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comentário não encontrado ou você não tem permissão para deletá-lo.")
    
    return {"message": "Comentário deletado com sucesso."}


# --------- AVALIAÇÕES E PERFIS ---------

@app.post("/avaliacoes", response_model=schemas.AvaliacaoResponse)
def avaliar(avaliacao: schemas.AvaliacaoCreate, db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user)):
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
def get_me_barbeiro(db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user)):
    barbeiro = crud.buscar_barbeiro_por_usuario_id(db, current_user.id)
    if not barbeiro:
        raise HTTPException(status_code=404, detail="Barbeiro não encontrado")
    return barbeiro

@app.put("/me/barbeiro", response_model=schemas.BarbeiroResponse)
def update_me_barbeiro(dados_update: schemas.BarbeiroUpdate, db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user)):
    barbeiro = crud.buscar_barbeiro_por_usuario_id(db, current_user.id)
    if not barbeiro:
        raise HTTPException(status_code=404, detail="Barbeiro não encontrado")
    return crud.atualizar_perfil_barbeiro(db, barbeiro, dados_update)

@app.put("/me/barbeiro/foto", response_model=schemas.BarbeiroResponse)
async def update_barbeiro_foto(
    file: UploadFile = File(...), # Recebe o arquivo diretamente como no /upload_foto
    db: Session = Depends(get_db), 
    current_user: models.Usuario = Depends(get_current_user)
):
    barbeiro = crud.buscar_barbeiro_por_usuario_id(db, current_user.id)
    if not barbeiro:
        raise HTTPException(status_code=404, detail="Barbeiro não encontrado")

    try:
        # ATENÇÃO AQUI: Acessando a variável global CLOUD_STORAGE_BUCKET_NAME_GLOBAL
        # e verificando se ela tem um valor antes de usar.
        if not CLOUD_STORAGE_BUCKET_NAME_GLOBAL:
            raise HTTPException(status_code=500, detail="Nome do bucket do Cloud Storage não configurado.")

        file_content = await file.read()
        filename_base = f"barbeiro_{barbeiro.id}-{os.path.splitext(file.filename)[0]}" 
        
        # Chama a nova função auxiliar para fazer upload e redimensionar, passando o bucket name
        uploaded_urls = await upload_and_resize_image(
            file_content=file_content,
            filename_base=filename_base,
            bucket_name=CLOUD_STORAGE_BUCKET_NAME_GLOBAL, # <-- Usando a variável GLOBAL corrigida
            content_type=file.content_type # Passa o content_type original do arquivo
        )
        
        # Atualiza o banco de dados com todas as URLs geradas
        return crud.atualizar_foto_barbeiro(
            db, 
            barbeiro, 
            foto_url_original=uploaded_urls.get("original"),
            foto_url_medium=uploaded_urls.get("medium"),
            foto_url_thumbnail=uploaded_urls.get("thumbnail")
        )

    except Exception as e:
        print(f"ERRO CRÍTICO NO UPLOAD DE FOTO DE BARBEIRO: {e}") 
        raise HTTPException(status_code=500, detail=f"Ocorreu um erro interno no servidor ao atualizar a foto: {e}")


@app.get("/me/agendamentos", response_model=List[schemas.AgendamentoResponse])
def listar_agendamentos_do_barbeiro(db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user)):
    barbeiro = crud.buscar_barbeiro_por_usuario_id(db, current_user.id)
    if not barbeiro:
        raise HTTPException(status_code=404, detail="Barbeiro não encontrado")
    return crud.listar_agendamentos_por_barbeiro(db, barbeiro.id)

@app.get("/me/horarios-trabalho", response_model=List[schemas.HorarioTrabalhoResponse])
def get_me_horarios_trabalho(db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user)):
    """
    Retorna os horários de trabalho definidos para o barbeiro autenticado.
    """
    barbeiro = crud.buscar_barbeiro_por_usuario_id(db, current_user.id)
    if not barbeiro:
        raise HTTPException(status_code=403, detail="Apenas barbeiros podem consultar horários de trabalho.")
    return crud.listar_horarios_trabalho(db, barbeiro.id)


# FUNÇÃO AUXILIAR PARA UPLOAD E REDIMENSIONAMENTO
async def upload_and_resize_image(
    file_content: bytes, 
    filename_base: str, 
    bucket_name: str,
    content_type: str # Adicionar content_type para garantir formato correto
) -> dict:
    """
    Faz o upload da imagem original e de versões redimensionadas para o GCS.
    Retorna um dicionário com as URLs de cada tamanho.
    """
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)

    urls = {}
    
    # Gerar a extensão do arquivo a partir do content_type ou do filename_base, por segurança
    # Assumindo que o content_type é 'image/jpeg' ou 'image/png'
    extension = ".jpeg"
    if "png" in content_type:
        extension = ".png"
    elif "gif" in content_type:
        extension = ".gif" # Adicionar suporte se necessário

    # Upload da imagem original
    original_blob_name = f"uploads/{filename_base}_original{extension}"
    original_blob = bucket.blob(original_blob_name)
    original_blob.upload_from_string(file_content, content_type=content_type)
    urls['original'] = f"https://storage.googleapis.com/{bucket_name}/{original_blob_name}"

    # Abrir a imagem para redimensionamento
    image = Image.open(BytesIO(file_content))
    # Converter para RGB se for PNG com RGBA, para evitar erros ao salvar como JPEG
    if image.mode == 'RGBA':
        image = image.convert('RGB')

    # Redimensionamento e Upload de versão média
    medium_size = (800, 800) # Exemplo: 800px de largura máxima, altura proporcional
    image_medium = image.copy() # Copia para não alterar a original
    image_medium.thumbnail(medium_size, Image.Resampling.LANCZOS) # Melhor qualidade de redimensionamento
    
    buffer_medium = BytesIO()
    # Salvar como JPEG para otimização, mesmo que a original fosse PNG
    image_medium.save(buffer_medium, format="JPEG", quality=85) 
    buffer_medium.seek(0)
    
    medium_blob_name = f"uploads/{filename_base}_medium.jpeg" # Sempre JPEG para versões otimizadas
    medium_blob = bucket.blob(medium_blob_name)
    medium_blob.upload_from_string(buffer_medium.getvalue(), content_type="image/jpeg")
    urls['medium'] = f"https://storage.googleapis.com/{bucket_name}/{medium_blob_name}"

    # Redimensionamento e Upload de thumbnail
    thumbnail_size = (200, 200) # Exemplo: 200x200 para thumbnails
    image_thumbnail = image.copy() # Abrir a original novamente (ou a RGB convertida)
    image_thumbnail.thumbnail(thumbnail_size, Image.Resampling.LANCZOS)
    
    buffer_thumbnail = BytesIO()
    image_thumbnail.save(buffer_thumbnail, format="JPEG", quality=85)
    buffer_thumbnail.seek(0)
    
    thumbnail_blob_name = f"uploads/{filename_base}_thumbnail.jpeg" # Sempre JPEG para versões otimizadas
    thumbnail_blob = bucket.blob(thumbnail_blob_name)
    thumbnail_blob.upload_from_string(buffer_thumbnail.getvalue(), content_type="image/jpeg")
    urls['thumbnail'] = f"https://storage.googleapis.com/{bucket_name}/{thumbnail_blob_name}"

    return urls

@app.post("/upload_foto")
async def upload_foto(file: UploadFile = File(...), current_user: models.Usuario = Depends(get_current_user)):
  try:
    # ATENÇÃO AQUI: Acessando a variável global CLOUD_STORAGE_BUCKET_NAME_GLOBAL
    # e verificando se ela tem um valor antes de usar.
    if not CLOUD_STORAGE_BUCKET_NAME_GLOBAL:
      raise HTTPException(status_code=500, detail="Nome do bucket do Cloud Storage não configurado.")

    file_content = await file.read()
    filename_base = f"{uuid.uuid4()}-{os.path.splitext(file.filename)[0]}" 
    
    uploaded_urls = await upload_and_resize_image(
      file_content=file_content,
      filename_base=filename_base,
      bucket_name=CLOUD_STORAGE_BUCKET_NAME_GLOBAL, # <-- Usando a variável GLOBAL corrigida
      content_type=file.content_type # Passa o content_type original do arquivo
    )

    return JSONResponse(content=uploaded_urls)

  except Exception as e:
    print(f"ERRO CRÍTICO NO UPLOAD: {e}") 
    raise HTTPException(status_code=500, detail=f"Ocorreu um erro interno no servidor: {e}")


# --------- DISPONIBILIDADE E HORÁRIOS ---------

@app.post("/me/horarios-trabalho", response_model=List[schemas.HorarioTrabalhoCreate])
def definir_horarios(horarios: List[schemas.HorarioTrabalhoCreate], db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user)):
  barbeiro = crud.buscar_barbeiro_por_usuario_id(db, current_user.id)
  if not barbeiro:
    raise HTTPException(status_code=403, detail="Apenas barbeiros podem definir horários.")
  return crud.definir_horarios_trabalho(db, barbeiro.id, horarios)

@app.post("/me/bloqueios", response_model=schemas.BloqueioResponse)
def criar_bloqueio(bloqueio: schemas.BloqueioCreate, db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user)):
    barbeiro = crud.buscar_barbeiro_por_usuario_id(db, current_user.id)
    if not barbeiro:
      raise HTTPException(status_code=403, detail="Apenas barbeiros podem criar bloqueios.")
    return crud.criar_bloqueio(db, barbeiro.id, bloqueio)

@app.delete("/me/bloqueios/{bloqueio_id}", status_code=204)
def deletar_bloqueio(bloqueio_id: uuid.UUID, db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user)):
  barbeiro = crud.buscar_barbeiro_por_usuario_id(db, current_user.id)
  if not barbeiro:
    raise HTTPException(status_code=403, detail="Acesso negado.")
  if not crud.deletar_bloqueio(db, bloqueio_id, barbeiro.id):
    raise HTTPException(status_code=404, detail="Bloqueio não encontrado.")
  return

@app.get("/barbeiros/{barbeiro_id}/horarios-disponiveis", response_model=List[time])
def get_horarios_disponiveis(barbeiro_id: uuid.UUID, dia: date, db: Session = Depends(get_db)):
  return crud.calcular_horarios_disponiveis(db, barbeiro_id, dia)


# --------- SERVIÇOS ---------

@app.post("/me/servicos", response_model=schemas.ServicoResponse)
def criar_servico(servico: schemas.ServicoCreate, db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user)):
  barbeiro = crud.buscar_barbeiro_por_usuario_id(db, current_user.id)
  if not barbeiro:
    raise HTTPException(status_code=403, detail="Apenas barbeiros podem criar serviços.")
  return crud.criar_servico(db, servico, barbeiro.id)

@app.get("/barbeiros/{barbeiro_id}/servicos", response_model=List[schemas.ServicoResponse])
def listar_servicos(barbeiro_id: uuid.UUID, db: Session = Depends(get_db)):
  return crud.listar_servicos_por_barbeiro(db, barbeiro_id)