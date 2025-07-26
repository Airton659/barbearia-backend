# barbearia-backend/main.py

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError
import models, schemas, crud
import uuid
import time
from auth import criar_token, get_current_user
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse
import httpx
from database import get_db, engine

app = FastAPI()

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
    
    token = criar_token({"sub": str(usuario.id)})
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


# --------- BARBEIROS ---------

@app.get("/barbeiros", response_model=List[schemas.BarbeiroResponse])
def listar_barbeiros(db: Session = Depends(get_db)):
    return crud.listar_barbeiros(db)

@app.post("/barbeiros", response_model=schemas.BarbeiroResponse)
def criar_barbeiro(barbeiro: schemas.BarbeiroCreate, db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user)):
    # Verifica se o usuário já é um barbeiro
    db_barbeiro = crud.buscar_barbeiro_por_usuario_id(db, current_user.id)
    if db_barbeiro:
        raise HTTPException(status_code=400, detail="Este usuário já é um barbeiro.")
    return crud.criar_barbeiro(db=db, barbeiro=barbeiro, usuario_id=current_user.id)


# --------- AGENDAMENTOS ---------

@app.post("/agendamentos", response_model=schemas.AgendamentoResponse)
def agendar(agendamento: schemas.AgendamentoCreate, db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user)):
    return crud.criar_agendamento(db, agendamento, usuario_id=current_user.id)

@app.get("/agendamentos", response_model=List[schemas.AgendamentoResponse])
def listar_agendamentos(db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user)):
    return crud.listar_agendamentos_por_usuario(db, current_user.id)


# --------- FEED / POSTAGENS ---------

@app.post("/postagens", response_model=schemas.PostagemResponse)
def criar_postagem(postagem: schemas.PostagemCreate, db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user)):
    barbeiro = crud.buscar_barbeiro_por_usuario_id(db, current_user.id)
    if not barbeiro:
        raise HTTPException(status_code=403, detail="Apenas barbeiros podem criar postagens")
    return crud.criar_postagem(db, postagem, barbeiro_id=barbeiro.id)

@app.get("/feed", response_model=List[schemas.PostagemResponse])
def listar_feed(db: Session = Depends(get_db), limit: int = 10, offset: int = 0):
    return crud.listar_feed(db, limit=limit, offset=offset)


# --------- CURTIDAS ---------

@app.post("/postagens/{postagem_id}/curtir")
def curtir_postagem(postagem_id: uuid.UUID, db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user)):
    resultado = crud.toggle_curtida(db, current_user.id, postagem_id)
    # Se a postagem não existia, o crud retorna None.
    if resultado is None and crud.buscar_postagem_por_id(db, postagem_id) is None:
        raise HTTPException(status_code=404, detail="Postagem não encontrada")
    return {"curtida": bool(resultado)}


# --------- COMENTÁRIOS ---------

@app.post("/comentarios", response_model=schemas.ComentarioResponse)
def comentar(comentario: schemas.ComentarioCreate, db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user)):
    return crud.criar_comentario(db, comentario, usuario_id=current_user.id)

@app.get("/comentarios/{postagem_id}", response_model=List[schemas.ComentarioResponse])
def listar_comentarios(postagem_id: uuid.UUID, db: Session = Depends(get_db)):
    return crud.listar_comentarios(db, postagem_id)


# --------- AVALIAÇÕES ---------

@app.post("/avaliacoes", response_model=schemas.AvaliacaoResponse)
def avaliar(avaliacao: schemas.AvaliacaoCreate, db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user)):
    return crud.criar_avaliacao(db, avaliacao, usuario_id=current_user.id)

@app.get("/avaliacoes/{barbeiro_id}", response_model=List[schemas.AvaliacaoResponse])
def listar_avaliacoes(barbeiro_id: uuid.UUID, db: Session = Depends(get_db)):
    return crud.listar_avaliacoes_barbeiro(db, barbeiro_id)


# --------- PERFIL DO BARBEIRO ---------

@app.get("/perfil_barbeiro/{barbeiro_id}", response_model=schemas.PerfilBarbeiroResponse)
def perfil_barbeiro(barbeiro_id: uuid.UUID, db: Session = Depends(get_db)):
    perfil = crud.obter_perfil_barbeiro(db, barbeiro_id)
    if not perfil or not perfil.get("barbeiro"):
        raise HTTPException(status_code=404, detail="Perfil do barbeiro não encontrado")
    return perfil

# --------- DADOS DO BARBEIRO LOGADO ---------

@app.get("/me/barbeiro", response_model=schemas.BarbeiroResponse)
def get_me_barbeiro(db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user)):
    barbeiro = crud.buscar_barbeiro_por_usuario_id(db, current_user.id)
    if not barbeiro:
        raise HTTPException(status_code=404, detail="Barbeiro não encontrado para o usuário logado")
    return barbeiro

# --------- AGENDAMENTOS DO BARBEIRO ---------

@app.get("/me/agendamentos", response_model=List[schemas.AgendamentoResponse])
def listar_agendamentos_do_barbeiro(db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user)):
    barbeiro = crud.buscar_barbeiro_por_usuario_id(db, current_user.id)
    if not barbeiro:
        raise HTTPException(status_code=404, detail="Barbeiro não encontrado")
    return crud.listar_agendamentos_por_barbeiro(db, barbeiro.id)


# --------- UPLOAD DE FOTOS VIA ImgBB ---------

IMGBB_API_KEY = "f75fe38ca523aab85bf5842130ccd27b"
IMGBB_UPLOAD_URL = "https://api.imgbb.com/1/upload"

@app.post("/upload_foto")
async def upload_foto(file: UploadFile = File(...)):
    contents = await file.read()
    async with httpx.AsyncClient() as client:
        response = await client.post(
            IMGBB_UPLOAD_URL,
            params={"key": IMGBB_API_KEY},
            files={"image": contents}
        )
    if response.status_code != 200:
        raise HTTPException(status_code=500, detail="Erro ao fazer upload da imagem")
    data = response.json()
    url = data["data"]["url"]
    return JSONResponse(content={"url": url})
