from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
import models, database, schemas, crud
import uuid
from uuid import uuid4
from auth import criar_token, get_current_user
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse
import httpx

app = FastAPI()

@app.on_event("startup")
def startup():
    models.Base.metadata.create_all(bind=database.engine)

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

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


# --------- BARBEIROS ---------

@app.get("/barbeiros", response_model=list[schemas.BarbeiroResponse])
def listar_barbeiros(db: Session = Depends(get_db)):
    return crud.listar_barbeiros(db)

@app.post("/barbeiros", response_model=schemas.BarbeiroResponse)
def criar_barbeiro(barbeiro: schemas.BarbeiroCreate, db: Session = Depends(get_db)):
    return crud.criar_barbeiro(db, barbeiro)


# --------- AGENDAMENTOS ---------

@app.post("/agendamentos", response_model=schemas.AgendamentoResponse)
def agendar(agendamento: schemas.AgendamentoCreate, db: Session = Depends(get_db)):
    return crud.criar_agendamento(db, agendamento)


# --------- FEED / POSTAGENS ---------

@app.post("/postagens", response_model=schemas.PostagemResponse)
def criar_postagem(postagem: schemas.PostagemCreate, db: Session = Depends(get_db)):
    return crud.criar_postagem(db, postagem)

@app.get("/feed", response_model=list[schemas.PostagemResponse])
def listar_feed(db: Session = Depends(get_db), limit: int = 10, offset: int = 0):
    return crud.listar_feed(db, limit=limit, offset=offset)


# --------- CURTIDAS ---------

@app.post("/postagens/{postagem_id}/curtir")
def curtir_postagem(postagem_id: uuid.UUID, usuario_id: uuid.UUID, db: Session = Depends(get_db)):
    resultado = crud.toggle_curtida(db, usuario_id, postagem_id)
    return {"curtida": bool(resultado)}


# --------- COMENTÁRIOS ---------

@app.post("/comentarios", response_model=schemas.ComentarioResponse)
def comentar(comentario: schemas.ComentarioCreate, db: Session = Depends(get_db)):
    return crud.criar_comentario(db, comentario)

@app.get("/comentarios/{postagem_id}", response_model=list[schemas.ComentarioResponse])
def listar_comentarios(postagem_id: uuid.UUID, db: Session = Depends(get_db)):
    return crud.listar_comentarios(db, postagem_id)


# --------- AVALIAÇÕES ---------

@app.post("/avaliacoes", response_model=schemas.AvaliacaoResponse)
def avaliar(avaliacao: schemas.AvaliacaoCreate, db: Session = Depends(get_db)):
    return crud.criar_avaliacao(db, avaliacao)

@app.get("/avaliacoes/{barbeiro_id}", response_model=list[schemas.AvaliacaoResponse])
def listar_avaliacoes(barbeiro_id: uuid.UUID, db: Session = Depends(get_db)):
    return crud.listar_avaliacoes_barbeiro(db, barbeiro_id)


# --------- PERFIL DO BARBEIRO ---------

@app.get("/perfil_barbeiro/{barbeiro_id}")
def perfil_barbeiro(barbeiro_id: uuid.UUID, db: Session = Depends(get_db)):
    return crud.obter_perfil_barbeiro(db, barbeiro_id)


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
