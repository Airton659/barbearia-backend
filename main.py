from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
import models, database, schemas, crud
import uuid

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
