from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
import models, database, schemas, crud

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


# --------- ROTAS ---------

@app.post("/usuarios", response_model=schemas.UsuarioResponse)
def criar_usuario(usuario: schemas.UsuarioCreate, db: Session = Depends(get_db)):
    existente = crud.buscar_usuario_por_email(db, usuario.email)
    if existente:
        raise HTTPException(status_code=400, detail="Email já cadastrado")
    return crud.criar_usuario(db, usuario)

@app.get("/barbeiros", response_model=list[schemas.BarbeiroResponse])
def listar_barbeiros(db: Session = Depends(get_db)):
    return crud.listar_barbeiros(db)

@app.post("/agendamentos", response_model=schemas.AgendamentoResponse)
def agendar(agendamento: schemas.AgendamentoCreate, db: Session = Depends(get_db)):
    return crud.criar_agendamento(db, agendamento)
