# barbearia-backend/main.py (Versão com Avaliações)

from fastapi import FastAPI, Depends, HTTPException, status, Header, Path, Query, UploadFile, File
from typing import List, Optional
import schemas, crud
import logging
from datetime import date
from database import initialize_firebase_app, get_db
from auth import get_current_user_firebase, get_super_admin_user, get_current_admin_user, get_current_profissional_user, get_optional_current_user_firebase, validate_negocio_id, validate_path_negocio_id
from firebase_admin import firestore
from pydantic import BaseModel
from google.cloud import storage
from PIL import Image
from io import BytesIO
import os
import uuid
from fastapi.responses import JSONResponse

# --- Modelo para a requisição de promoção ---
class PromoteRequest(BaseModel):
    firebase_uid: str

# --- Configuração da Aplicação ---
app = FastAPI(
    title="API de Agendamento Multi-Tenant",
    description="Backend para múltiplos negócios de agendamento, usando Firebase e Firestore.",
    version="2.0.0"
)

# Adicionar um logger para ajudar no debug
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CLOUD_STORAGE_BUCKET_NAME_GLOBAL = os.getenv("CLOUD_STORAGE_BUCKET_NAME")


# --- Evento de Startup ---
@app.on_event("startup")
def startup_event():
    """Inicializa a conexão com o Firebase ao iniciar a aplicação."""
    initialize_firebase_app()

# --- Endpoint Raiz ---
@app.get("/")
def root():
    return {"mensagem": "API de Agendamento Multi-Tenant funcionando", "versao": "2.0.0"}

# =================================================================================
# ENDPOINTS DE ADMINISTRAÇÃO DA PLATAFORMA (SUPER-ADMIN)
# =================================================================================

@app.post("/admin/negocios", response_model=schemas.NegocioResponse, tags=["Admin - Plataforma"])
def admin_criar_negocio(
    negocio_data: schemas.NegocioCreate,
    admin: schemas.UsuarioProfile = Depends(get_super_admin_user),
    db: firestore.client = Depends(get_db)
):
    """
    (Super-Admin) Cria um novo negócio na plataforma e retorna os dados,
    incluindo o código de convite para o dono do negócio.
    """
    return crud.admin_criar_negocio(db, negocio_data, admin.firebase_uid)

@app.get("/admin/negocios", response_model=List[schemas.NegocioResponse], tags=["Admin - Plataforma"])
def admin_listar_negocios(
    admin: schemas.UsuarioProfile = Depends(get_super_admin_user),
    db: firestore.client = Depends(get_db)
):
    """(Super-Admin) Lista todos os negócios cadastrados na plataforma."""
    return crud.admin_listar_negocios(db)

# =================================================================================
# ENDPOINTS DE GERENCIAMENTO DO NEGÓCIO (ADMIN DE NEGÓCIO)
# =================================================================================

@app.get("/negocios/{negocio_id}/usuarios", response_model=List[schemas.UsuarioProfile], tags=["Admin - Gestão do Negócio"])
def listar_usuarios_do_negocio(
    negocio_id: str = Depends(validate_path_negocio_id),
    admin: schemas.UsuarioProfile = Depends(get_current_admin_user),
    db: firestore.client = Depends(get_db)
):
    """(Admin de Negócio) Lista todos os usuários (clientes e profissionais) do seu negócio."""
    return crud.admin_listar_usuarios_por_negocio(db, negocio_id)

@app.get("/negocios/{negocio_id}/clientes", response_model=List[schemas.UsuarioProfile], tags=["Admin - Gestão do Negócio"])
def listar_clientes_do_negocio(
    negocio_id: str = Depends(validate_path_negocio_id),
    admin: schemas.UsuarioProfile = Depends(get_current_admin_user),
    db: firestore.client = Depends(get_db)
):
    """(Admin de Negócio) Lista todos os usuários com o papel de 'cliente' no seu negócio."""
    return crud.admin_listar_clientes_por_negocio(db, negocio_id)

@app.post("/negocios/{negocio_id}/promover", response_model=schemas.UsuarioProfile, tags=["Admin - Gestão do Negócio"])
def promover_cliente(
    request_body: PromoteRequest,
    negocio_id: str = Depends(validate_path_negocio_id),
    admin: schemas.UsuarioProfile = Depends(get_current_admin_user),
    db: firestore.client = Depends(get_db)
):
    """(Admin de Negócio) Promove um usuário de 'cliente' para 'profissional'."""
    usuario_promovido = crud.admin_promover_cliente_para_profissional(db, negocio_id, request_body.firebase_uid)
    if not usuario_promovido:
        raise HTTPException(status_code=404, detail="Usuário não encontrado ou não é um cliente deste negócio.")
    return usuario_promovido

@app.post("/negocios/{negocio_id}/rebaixar", response_model=schemas.UsuarioProfile, tags=["Admin - Gestão do Negócio"])
def rebaixar_profissional(
    request_body: PromoteRequest,
    negocio_id: str = Depends(validate_path_negocio_id),
    admin: schemas.UsuarioProfile = Depends(get_current_admin_user),
    db: firestore.client = Depends(get_db)
):
    """(Admin de Negócio) Rebaixa um usuário de 'profissional' para 'cliente'."""
    usuario_rebaixado = crud.admin_rebaixar_profissional_para_cliente(db, negocio_id, request_body.firebase_uid)
    if not usuario_rebaixado:
        raise HTTPException(status_code=404, detail="Usuário não encontrado ou não é um profissional deste negócio.")
    return usuario_rebaixado

@app.post("/negocios/{negocio_id}/medicos", response_model=schemas.MedicoResponse, tags=["Admin - Gestão do Negócio"])
def criar_medico(
    medico_data: schemas.MedicoBase,
    negocio_id: str = Depends(validate_path_negocio_id),
    admin: schemas.UsuarioProfile = Depends(get_current_admin_user),
    db: firestore.client = Depends(get_db)
):
    """(Admin de Negócio) Cadastra um novo médico de referência para a clínica."""
    medico_data.negocio_id = negocio_id
    return crud.criar_medico(db, medico_data)

@app.get("/negocios/{negocio_id}/medicos", response_model=List[schemas.MedicoResponse], tags=["Admin - Gestão do Negócio"])
def listar_medicos(
    negocio_id: str = Depends(validate_path_negocio_id),
    admin: schemas.UsuarioProfile = Depends(get_current_admin_user),
    db: firestore.client = Depends(get_db)
):
    """(Admin de Negócio) Lista todos os médicos de referência da clínica."""
    return crud.listar_medicos_por_negocio(db, negocio_id)

# =================================================================================
# ENDPOINTS DE AUTOGESTÃO DO PROFISSIONAL
# =================================================================================

@app.get("/me/profissional", response_model=schemas.ProfissionalResponse, tags=["Profissional - Autogestão"])
def get_meu_perfil_profissional(
    negocio_id: str = Depends(validate_negocio_id),
    profissional_user: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """(Profissional) Retorna o seu próprio perfil profissional."""
    perfil = crud.buscar_profissional_por_uid(db, negocio_id, profissional_user.firebase_uid)
    if not perfil:
        raise HTTPException(status_code=404, detail="Perfil profissional não encontrado para este usuário neste negócio.")
    return perfil

@app.put("/me/profissional", response_model=schemas.ProfissionalResponse, tags=["Profissional - Autogestão"])
def update_meu_perfil_profissional(
    update_data: schemas.ProfissionalUpdate,
    negocio_id: str = Depends(validate_negocio_id),
    profissional_user: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """(Profissional) Atualiza o seu próprio perfil profissional."""
    perfil_atual = crud.buscar_profissional_por_uid(db, negocio_id, profissional_user.firebase_uid)
    if not perfil_atual:
        raise HTTPException(status_code=404, detail="Perfil profissional não encontrado para este usuário neste negócio.")
    
    perfil_atualizado = crud.atualizar_perfil_profissional(db, perfil_atual['id'], update_data)
    return perfil_atualizado

@app.post("/me/servicos", response_model=schemas.ServicoResponse, status_code=status.HTTP_201_CREATED, tags=["Profissional - Autogestão"])
def criar_meu_servico(
    servico_data: schemas.ServicoCreate,
    negocio_id: str = Depends(validate_negocio_id),
    profissional_user: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """(Profissional) Cria um novo serviço associado ao seu perfil."""
    perfil_profissional = crud.buscar_profissional_por_uid(db, negocio_id, profissional_user.firebase_uid)
    if not perfil_profissional:
        raise HTTPException(status_code=404, detail="Perfil profissional não encontrado.")

    # Garante que o serviço seja criado para o profissional e negócio corretos, ignorando o que vier do body
    servico_data.profissional_id = perfil_profissional['id']
    servico_data.negocio_id = negocio_id
    
    return crud.criar_servico(db, servico_data)

@app.get("/me/servicos", response_model=List[schemas.ServicoResponse], tags=["Profissional - Autogestão"])
def listar_meus_servicos(
    negocio_id: str = Depends(validate_negocio_id),
    profissional_user: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """(Profissional) Lista todos os serviços associados ao seu perfil."""
    perfil_profissional = crud.buscar_profissional_por_uid(db, negocio_id, profissional_user.firebase_uid)
    if not perfil_profissional:
        raise HTTPException(status_code=404, detail="Perfil profissional não encontrado.")
        
    return crud.listar_servicos_por_profissional(db, perfil_profissional['id'])

@app.put("/me/servicos/{servico_id}", response_model=schemas.ServicoResponse, tags=["Profissional - Autogestão"])
def atualizar_meu_servico(
    servico_id: str,
    update_data: schemas.ServicoUpdate,
    negocio_id: str = Depends(validate_negocio_id),
    profissional_user: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """(Profissional) Atualiza um de seus serviços."""
    perfil_atual = crud.buscar_profissional_por_uid(db, negocio_id, profissional_user.firebase_uid)
    if not perfil_atual:
        raise HTTPException(status_code=404, detail="Perfil profissional não encontrado.")
    
    servico_atualizado = crud.atualizar_servico(db, servico_id, perfil_atual['id'], update_data)
    if not servico_atualizado:
        raise HTTPException(status_code=403, detail="Serviço não encontrado ou não pertence a este profissional.")
        
    return servico_atualizado

@app.delete("/me/servicos/{servico_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Profissional - Autogestão"])
def deletar_meu_servico(
    servico_id: str,
    negocio_id: str = Depends(validate_negocio_id),
    profissional_user: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """(Profissional) Deleta um de seus serviços."""
    perfil_profissional = crud.buscar_profissional_por_uid(db, negocio_id, profissional_user.firebase_uid)
    if not perfil_profissional:
        raise HTTPException(status_code=404, detail="Perfil profissional não encontrado.")
        
    if not crud.deletar_servico(db, servico_id, perfil_profissional['id']):
        raise HTTPException(status_code=403, detail="Serviço não encontrado ou não pertence a este profissional.")
    
    return

@app.post("/me/horarios-trabalho", response_model=List[schemas.HorarioTrabalho], tags=["Profissional - Autogestão"])
def definir_meus_horarios(
    horarios: List[schemas.HorarioTrabalho],
    negocio_id: str = Depends(validate_negocio_id),
    profissional_user: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """(Profissional) Define sua grade de horários de trabalho semanal."""
    perfil_profissional = crud.buscar_profissional_por_uid(db, negocio_id, profissional_user.firebase_uid)
    if not perfil_profissional:
        raise HTTPException(status_code=404, detail="Perfil profissional não encontrado.")

    return crud.definir_horarios_trabalho(db, perfil_profissional['id'], horarios)

@app.get("/me/horarios-trabalho", response_model=List[schemas.HorarioTrabalho], tags=["Profissional - Autogestão"])
def get_meus_horarios(
    negocio_id: str = Depends(validate_negocio_id),
    profissional_user: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """(Profissional) Lista sua grade de horários de trabalho."""
    perfil_profissional = crud.buscar_profissional_por_uid(db, negocio_id, profissional_user.firebase_uid)
    if not perfil_profissional:
        raise HTTPException(status_code=404, detail="Perfil profissional não encontrado.")

    return crud.listar_horarios_trabalho(db, perfil_profissional['id'])

@app.post("/me/bloqueios", response_model=schemas.Bloqueio, tags=["Profissional - Autogestão"])
def criar_meu_bloqueio(
    bloqueio_data: schemas.Bloqueio,
    negocio_id: str = Depends(validate_negocio_id),
    profissional_user: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """(Profissional) Cria um bloqueio em sua agenda."""
    perfil_profissional = crud.buscar_profissional_por_uid(db, negocio_id, profissional_user.firebase_uid)
    if not perfil_profissional:
        raise HTTPException(status_code=404, detail="Perfil profissional não encontrado.")
    
    return crud.criar_bloqueio(db, perfil_profissional['id'], bloqueio_data)

@app.delete("/me/bloqueios/{bloqueio_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Profissional - Autogestão"])
def deletar_meu_bloqueio(
    bloqueio_id: str,
    negocio_id: str = Depends(validate_negocio_id),
    profissional_user: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """(Profissional) Deleta um bloqueio de sua agenda."""
    perfil_profissional = crud.buscar_profissional_por_uid(db, negocio_id, profissional_user.firebase_uid)
    if not perfil_profissional:
        raise HTTPException(status_code=404, detail="Perfil profissional não encontrado.")
        
    if not crud.deletar_bloqueio(db, perfil_profissional['id'], bloqueio_id):
        raise HTTPException(status_code=404, detail="Bloqueio não encontrado.")
    
    return

# =================================================================================
# ENDPOINTS DE FEED E INTERAÇÕES
# =================================================================================

@app.post("/postagens", response_model=schemas.PostagemResponse, tags=["Feed e Interações"])
def criar_postagem(
    postagem_data: schemas.PostagemCreate,
    negocio_id: str = Depends(validate_negocio_id),
    profissional_user: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """(Profissional) Cria uma nova postagem no feed do negócio."""
    perfil_profissional = crud.buscar_profissional_por_uid(db, negocio_id, profissional_user.firebase_uid)
    if not perfil_profissional:
        raise HTTPException(status_code=404, detail="Perfil profissional não encontrado para este usuário neste negócio.")
    
    postagem_data.profissional_id = perfil_profissional['id']
    postagem_data.negocio_id = negocio_id
    
    return crud.criar_postagem(db, postagem_data, perfil_profissional)

@app.get("/feed", response_model=List[schemas.PostagemResponse], tags=["Feed e Interações"])
def get_feed(
    negocio_id: str,
    db: firestore.client = Depends(get_db),
    current_user: Optional[schemas.UsuarioProfile] = Depends(get_optional_current_user_firebase)
):
    """(Público) Retorna o feed de postagens de um negócio específico."""
    user_id = current_user.id if current_user else None
    return crud.listar_feed_por_negocio(db, negocio_id, user_id)

@app.post("/postagens/{postagem_id}/curtir", tags=["Feed e Interações"])
def curtir_postagem(
    postagem_id: str,
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """(Autenticado) Curte ou descurte uma postagem."""
    resultado = crud.toggle_curtida(db, postagem_id, current_user.id)
    return {"curtido": resultado}

@app.post("/comentarios", response_model=schemas.ComentarioResponse, tags=["Feed e Interações"])
def criar_comentario(
    comentario_data: schemas.ComentarioCreate,
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """(Autenticado) Adiciona um comentário a uma postagem."""
    return crud.criar_comentario(db, comentario_data, current_user)

@app.get("/comentarios/{postagem_id}", response_model=List[schemas.ComentarioResponse], tags=["Feed e Interações"])
def get_comentarios(
    postagem_id: str,
    db: firestore.client = Depends(get_db)
):
    """(Público) Lista todos os comentários de uma postagem."""
    return crud.listar_comentarios(db, postagem_id)

@app.delete("/postagens/{postagem_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Feed e Interações"])
def deletar_postagem(
    postagem_id: str,
    negocio_id: str = Depends(validate_negocio_id),
    profissional_user: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """(Profissional) Deleta uma de suas postagens."""
    perfil_profissional = crud.buscar_profissional_por_uid(db, negocio_id, profissional_user.firebase_uid)
    if not perfil_profissional:
        raise HTTPException(status_code=404, detail="Perfil profissional não encontrado.")
        
    if not crud.deletar_postagem(db, postagem_id, perfil_profissional['id']):
        raise HTTPException(status_code=403, detail="Postagem não encontrada ou não pertence a este profissional.")
    
    return

@app.delete("/comentarios/{comentario_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Feed e Interações"])
def deletar_comentario(
    comentario_id: str,
    postagem_id: str = Query(..., description="ID da postagem à qual o comentário pertence."),
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """(Autenticado) Deleta um de seus comentários."""
    if not crud.deletar_comentario(db, postagem_id, comentario_id, current_user.id):
        raise HTTPException(status_code=403, detail="Comentário não encontrado ou você não tem permissão para deletá-lo.")
        
    return

# =================================================================================
# ENDPOINTS DE AVALIAÇÕES
# =================================================================================

@app.post("/avaliacoes", response_model=schemas.AvaliacaoResponse, status_code=status.HTTP_201_CREATED, tags=["Avaliações"])
def criar_avaliacao(
    avaliacao_data: schemas.AvaliacaoCreate,
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """(Cliente) Cria uma nova avaliação para um profissional."""
    return crud.criar_avaliacao(db, avaliacao_data, current_user)

@app.get("/avaliacoes/{profissional_id}", response_model=List[schemas.AvaliacaoResponse], tags=["Avaliações"])
def listar_avaliacoes(
    profissional_id: str,
    db: firestore.client = Depends(get_db)
):
    """(Público) Lista todas as avaliações de um profissional."""
    return crud.listar_avaliacoes_por_profissional(db, profissional_id)

# =================================================================================
# ENDPOINTS DE NOTIFICAÇÕES
# =================================================================================

@app.get("/notificacoes", response_model=List[schemas.NotificacaoResponse], tags=["Notificações"])
def get_notificacoes(
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """(Autenticado) Retorna o histórico de notificações do usuário."""
    return crud.listar_notificacoes(db, current_user.id)

@app.get("/notificacoes/nao-lidas/contagem", response_model=schemas.NotificacaoContagemResponse, tags=["Notificações"])
def get_contagem_notificacoes_nao_lidas(
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """(Autenticado) Retorna o número de notificações não lidas."""
    count = crud.contar_notificacoes_nao_lidas(db, current_user.id)
    return {"count": count}

@app.post("/notificacoes/ler-todas", status_code=status.HTTP_204_NO_CONTENT, tags=["Notificações"])
def marcar_todas_como_lidas(
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """(Autenticado) Marca todas as notificações do usuário como lidas."""
    crud.marcar_todas_como_lidas(db, current_user.id)
    return

@app.post("/notificacoes/marcar-como-lida", status_code=status.HTTP_204_NO_CONTENT, tags=["Notificações"])
def marcar_como_lida(
    request: schemas.MarcarLidaRequest,
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """(Autenticado) Marca uma notificação específica como lida."""
    crud.marcar_notificacao_como_lida(db, current_user.id, request.notificacao_id)
    return

# =================================================================================
# ENDPOINTS DE USUÁRIOS E AUTENTICAÇÃO
# =================================================================================

@app.post("/users/sync-profile", response_model=schemas.UsuarioProfile, tags=["Usuários"])
def sync_user_profile(
    user_data: schemas.UsuarioSync,
    db: firestore.client = Depends(get_db)
):
    """
    Sincroniza os dados do usuário do Firebase Auth com o Firestore.
    Cria um perfil de usuário no banco de dados na primeira vez que ele faz login.
    """
    try:
        user_profile = crud.criar_ou_atualizar_usuario(db, user_data)
        
        # Verifica se o usuário foi promovido a admin
        if user_data.codigo_convite and user_profile:
            negocio_id = user_profile.get('roles', {}).keys()
            if negocio_id:
                negocio_id = list(negocio_id)[0]
                if user_profile['roles'].get(negocio_id) == "admin":
                    # Se for admin, cria o perfil de profissional
                    profissional_data = schemas.ProfissionalCreate(
                        negocio_id=negocio_id,
                        usuario_uid=user_profile['firebase_uid'],
                        nome=user_profile['nome'],
                        especialidades="A definir",
                        ativo=True,
                        fotos={}
                    )
                    crud.criar_profissional(db, profissional_data)
                    logger.info(f"Perfil profissional criado para o novo admin: {user_profile['email']}")

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Erro inesperado ao sincronizar perfil do usuário: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ocorreu um erro interno no servidor.")

    return user_profile

@app.get("/me/profile", response_model=schemas.UsuarioProfile, tags=["Usuários"])
def get_me_profile(current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase)):
    """Retorna o perfil completo do usuário autenticado."""
    return current_user

@app.post("/me/register-fcm-token", status_code=status.HTTP_200_OK, tags=["Usuários"])
def register_fcm_token_endpoint(
    request: schemas.FCMTokenUpdate,
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """Registra ou atualiza o token de notificação (FCM) para o dispositivo do usuário."""
    crud.adicionar_fcm_token(db, current_user.firebase_uid, request.fcm_token)
    return {"message": "FCM token registrado com sucesso."}

@app.get("/negocios/{negocio_id}/admin-status", tags=["Admin - Gestão do Negócio"])
def get_admin_status(
    negocio_id: str,
    db: firestore.client = Depends(get_db)
):
    """
    (Público) Verifica se um negócio já possui um administrador.
    """
    has_admin = crud.check_admin_status(db, negocio_id)
    return {"has_admin": has_admin}

# =================================================================================
# ENDPOINTS DE PROFISSIONAIS (Públicos)
# =================================================================================

@app.get("/profissionais", response_model=List[schemas.ProfissionalResponse], tags=["Profissionais"])
def listar_profissionais(
    negocio_id: str,
    db: firestore.client = Depends(get_db)
):
    """Lista todos os profissionais ativos de um negócio específico."""
    return crud.listar_profissionais_por_negocio(db, negocio_id)

@app.get("/profissionais/{profissional_id}", response_model=schemas.ProfissionalResponse, tags=["Profissionais"])
def get_profissional_details(
    profissional_id: str,
    db: firestore.client = Depends(get_db)
):
    """Retorna os detalhes de um profissional específico, incluindo seus serviços."""
    profissional = crud.buscar_profissional_por_id(db, profissional_id)
    if not profissional:
        raise HTTPException(status_code=404, detail="Profissional não encontrado.")
    
    servicos = crud.listar_servicos_por_profissional(db, profissional_id)
    profissional['servicos'] = servicos
    
    postagens = crud.listar_postagens_por_profissional(db, profissional_id)
    profissional['postagens'] = postagens
    
    avaliacoes = crud.listar_avaliacoes_por_profissional(db, profissional_id)
    profissional['avaliacoes'] = avaliacoes
    
    return profissional

# =================================================================================
# ENDPOINTS DE AGENDAMENTOS E DISPONIBILIDADE PÚBLICA
# =================================================================================

@app.get("/profissionais/{profissional_id}/horarios-disponiveis", tags=["Agendamentos"])
def get_horarios_disponiveis(
    profissional_id: str,
    dia: date = Query(..., description="Dia para verificar a disponibilidade (formato: AAAA-MM-DD)."),
    duracao_servico: int = Query(60, description="Duração do serviço em minutos para calcular os slots."),
    db: firestore.client = Depends(get_db)
):
    """(Público) Calcula e retorna os horários livres de um profissional em um dia específico."""
    return crud.calcular_horarios_disponiveis(db, profissional_id, dia, duracao_servico)

@app.post("/agendamentos", response_model=schemas.AgendamentoResponse, tags=["Agendamentos"])
def agendar(
    agendamento: schemas.AgendamentoCreate,
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """(Cliente) Cria um novo agendamento para o usuário autenticado."""
    try:
        novo_agendamento = crud.criar_agendamento(db, agendamento, current_user)
        return novo_agendamento
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Erro inesperado ao criar agendamento: {e}")
        raise HTTPException(status_code=500, detail="Ocorreu um erro ao criar o agendamento.")

@app.get("/agendamentos/me", response_model=List[schemas.AgendamentoResponse], tags=["Agendamentos"])
def listar_meus_agendamentos_cliente(
    negocio_id: str = Header(..., description="ID do Negócio para filtrar os agendamentos."),
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """(Cliente) Lista todos os agendamentos do cliente autenticado em um negócio específico."""
    return crud.listar_agendamentos_por_cliente(db, negocio_id, current_user.id)

@app.delete("/agendamentos/{agendamento_id}", status_code=status.HTTP_200_OK, tags=["Agendamentos"])
def cancelar_agendamento_endpoint(
    agendamento_id: str,
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """(Cliente) Permite ao cliente autenticado cancelar um de seus agendamentos."""
    agendamento_cancelado = crud.cancelar_agendamento(db, agendamento_id, current_user.id)
    
    if agendamento_cancelado is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agendamento não encontrado ou você não tem permissão para cancelá-lo."
        )
    
    return {"message": "Agendamento cancelado com sucesso."}

@app.get("/me/agendamentos", response_model=List[schemas.AgendamentoResponse], tags=["Profissional - Autogestão"])
def listar_meus_agendamentos_profissional(
    negocio_id: str = Header(..., description="ID do Negócio no qual o profissional está atuando."),
    profissional_user: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """(Profissional) Lista todos os agendamentos recebidos pelo profissional."""
    perfil_profissional = crud.buscar_profissional_por_uid(db, negocio_id, profissional_user.firebase_uid)
    if not perfil_profissional:
        raise HTTPException(status_code=404, detail="Perfil profissional não encontrado.")
    
    return crud.listar_agendamentos_por_profissional(db, negocio_id, perfil_profissional['id'])

@app.patch("/me/agendamentos/{agendamento_id}/cancelar", response_model=schemas.AgendamentoResponse, tags=["Profissional - Autogestão"])
def cancelar_agendamento_pelo_profissional_endpoint(
    agendamento_id: str,
    negocio_id: str = Header(..., description="ID do Negócio no qual o profissional está atuando."),
    profissional_user: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """(Profissional) Cancela um agendamento que recebeu."""
    perfil_profissional = crud.buscar_profissional_por_uid(db, negocio_id, profissional_user.firebase_uid)
    if not perfil_profissional:
        raise HTTPException(status_code=404, detail="Perfil profissional não encontrado.")
    
    agendamento_cancelado = crud.cancelar_agendamento_pelo_profissional(db, agendamento_id, perfil_profissional['id'])
    if not agendamento_cancelado:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado ou não pertence a este profissional.")
        
    return agendamento_cancelado

# =================================================================================
# ENDPOINT DE UPLOAD DE FOTOS
# =================================================================================

async def upload_and_resize_image(
    file_content: bytes,
    filename_base: str,
    bucket_name: str,
    content_type: str
) -> dict:
    """Função auxiliar para upload e redimensionamento de imagens no Cloud Storage."""
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    urls = {}
    extension = ".jpeg" # Forçar JPEG para redimensionamento
    
    image = Image.open(BytesIO(file_content))
    if image.mode in ('RGBA', 'P'):
        image = image.convert('RGB')

    buffer_original = BytesIO()
    image.save(buffer_original, format="JPEG", quality=90)
    buffer_original.seek(0)
    original_blob_name = f"uploads/{filename_base}_original{extension}"
    original_blob = bucket.blob(original_blob_name)
    original_blob.upload_from_string(buffer_original.getvalue(), content_type="image/jpeg")
    urls['original'] = original_blob.public_url

    image.thumbnail((800, 800))
    buffer_medium = BytesIO()
    image.save(buffer_medium, format="JPEG", quality=85)
    buffer_medium.seek(0)
    medium_blob_name = f"uploads/{filename_base}_medium{extension}"
    medium_blob = bucket.blob(medium_blob_name)
    medium_blob.upload_from_string(buffer_medium.getvalue(), content_type="image/jpeg")
    urls['medium'] = medium_blob.public_url

    image.thumbnail((200, 200))
    buffer_thumbnail = BytesIO()
    image.save(buffer_thumbnail, format="JPEG", quality=80)
    buffer_thumbnail.seek(0)
    thumbnail_blob_name = f"uploads/{filename_base}_thumbnail{extension}"
    thumbnail_blob = bucket.blob(thumbnail_blob_name)
    thumbnail_blob.upload_from_string(buffer_thumbnail.getvalue(), content_type="image/jpeg")
    urls['thumbnail'] = thumbnail_blob.public_url

    return urls

@app.post("/upload-foto", tags=["Utilitários"])
async def upload_foto(
    file: UploadFile = File(...),
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase)
):
    """(Autenticado) Faz o upload de uma foto, redimensiona e retorna as URLs."""
    if not CLOUD_STORAGE_BUCKET_NAME_GLOBAL:
        raise HTTPException(status_code=500, detail="Bucket do Cloud Storage não configurado.")
    
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