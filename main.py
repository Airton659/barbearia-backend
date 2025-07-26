from fastapi import FastAPI
from . import models, database

app = FastAPI()

@app.on_event("startup")
def startup():
    models.Base.metadata.create_all(bind=database.engine)

@app.get("/")
def root():
    return {"mensagem": "API da barbearia funcionando"}
