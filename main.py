from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
import models, schemas, crud
import uuid
from auth import criar_token, get_current_user
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse
import httpx
# Alteração 1: Importar get_db e engine do local centralizado
from database import get_db, engine

app = FastAPI()

@app.on_event("startup")
def startup():
    models.Base.metadata.create_all(bind=engine)

# Alteração 2: A função get_db foi removida daqui

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

# Alteração 3: Corrigido para montar a resposta com o nome do usuário
@app.get("/barbeiros", response_model=list[schemas.BarbeiroResponse])
def listar_barbeiros(db: Session = Depends(get_db)):
    barbeiros_from_db = crud.listar_barbeiros(db)
    
    # Monta a resposta manualmente para incluir o nome do usuário associado
    response = []
    for barbeiro in barbeiros_from_db:
        # Garante que o barbeiro tem um usuário associado antes de tentar acessá-lo
        if barbeiro.usuario:
            response.append(
                schemas.BarbeiroResponse(
                    id=barbeiro.id,
                    nome=barbeiro.usuario.nome, # Pega o nome do usuário
                    especialidades=barbeiro.especialidades,
                    foto=barbeiro.foto,
                    ativo=barbeiro.ativo,
                )
            )
    return response

# Alteração 4: Corrigido para associar o barbeiro ao usuário logado
@app.post("/barbeiros", response_model=schemas.BarbeiroResponse)
def criar_barbeiro(barbeiro: schemas.BarbeiroCreate, db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user)):
    # A lógica de criação será ajustada no crud.py para receber o usuario_id
    novo_barbeiro = crud.criar_barbeiro(db=db, barbeiro=barbeiro, usuario_id=current_user.id)
    if not novo_barbeiro.usuario:
        # Se a relação não foi carregada, busca novamente para garantir a resposta completa
        db.refresh(novo_barbeiro, ["usuario"])

    return schemas.BarbeiroResponse(
        id=novo_barbeiro.id,
        nome=novo_barbeiro.usuario.nome,
        especialidades=novo_barbeiro.especialidades,
        foto=novo_barbeiro.foto,
        ativo=novo_barbeiro.ativo,
    )


# --------- AGENDAMENTOS ---------

@app.post("/agendamentos", response_model=schemas.AgendamentoResponse)
def agendar(agendamento: schemas.AgendamentoCreate, db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user)):
    # Esta linha está incorreta, pois o schema não tem `usuario_id`
    # A atribuição será feita dentro da função crud
    return crud.criar_agendamento(db, agendamento, usuario_id=current_user.id)

@app.get("/agendamentos", response_model=list[schemas.AgendamentoResponse])
def listar_agendamentos(db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user)):
    return crud.listar_agendamentos_por_usuario(db, current_user.id)


# --------- FEED / POSTAGENS ---------

@app.post("/postagens", response_model=schemas.PostagemResponse)
def criar_postagem(postagem: schemas.PostagemCreate, db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user)):
    # Precisamos garantir que o usuário logado é um barbeiro
    barbeiro = crud.buscar_barbeiro_por_usuario_id(db, current_user.id)
    if not barbeiro:
        raise HTTPException(status_code=403, detail="Apenas barbeiros podem criar postagens")
    return crud.criar_postagem(db, postagem, barbeiro_id=barbeiro.id)

@app.get("/feed", response_model=list[schemas.PostagemResponse])
def listar_feed(db: Session = Depends(get_db), limit: int = 10, offset: int = 0):
    return crud.listar_feed(db, limit=limit, offset=offset)


# --------- CURTIDAS ---------

@app.post("/postagens/{postagem_id}/curtir")
def curtir_postagem(postagem_id: uuid.UUID, db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user)):
    resultado = crud.toggle_curtida(db, current_user.id, postagem_id)
    return {"curtida": bool(resultado)}


# --------- COMENTÁRIOS ---------

@app.post("/comentarios", response_model=schemas.ComentarioResponse)
def comentar(comentario: schemas.ComentarioCreate, db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user)):
    # A atribuição do usuario_id será feita na função crud
    return crud.criar_comentario(db, comentario, usuario_id=current_user.id)

@app.get("/comentarios/{postagem_id}", response_model=list[schemas.ComentarioResponse])
def listar_comentarios(postagem_id: uuid.UUID, db: Session = Depends(get_db)):
    return crud.listar_comentarios(db, postagem_id)


# --------- AVALIAÇÕES ---------

@app.post("/avaliacoes", response_model=schemas.AvaliacaoResponse)
def avaliar(avaliacao: schemas.AvaliacaoCreate, db: Session = Depends(get_db), current_user: models.Usuario = Depends(get_current_user)):
    # A atribuição do usuario_id será feita na função crud
    return crud.criar_avaliacao(db, avaliacao, usuario_id=current_user.id)

@app.get("/avaliacoes/{barbeiro_id}", response_model=list[schemas.AvaliacaoResponse])
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
    if not barbeiro or not barbeiro.usuario:
        raise HTTPException(status_code=404, detail="Barbeiro não encontrado para o usuário logado")
    
    return schemas.BarbeiroResponse(
        id=barbeiro.id,
        nome=barbeiro.usuario.nome,
        especialidades=barbeiro.especialidades,
        foto=barbeiro.foto,
        ativo=barbeiro.ativo
    )

# --------- AGENDAMENTOS DO BARBEIRO ---------

@app.get("/me/agendamentos", response_model=list[schemas.AgendamentoResponse])
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