# main_modular.py - Versão Modular da API
"""
FastAPI modular organizada com routers separados por domínio de negócio.
"""

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import os
import logging
from database import initialize_firebase_app

# Importar todos os routers
from routers import (
    admin,
    auth,
    profissionais,
    agendamentos,
    pacientes,
    medicos,
    interacoes,
    notifications,
    utilitarios,
    servicos
)

# --- Configuração da Aplicação ---
app = FastAPI(
    title="API de Agendamento Multi-Tenant",
    description="Backend modular para múltiplos negócios de agendamento, usando Firebase e Firestore.",
    version="3.0.0"  # Versão modular
)

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Evento de Startup ---
@app.on_event("startup")
def startup_event():
    """Inicializa a conexão com o Firebase ao iniciar a aplicação."""
    initialize_firebase_app()
    logger.info("🚀 API Modular iniciada com sucesso!")

# --- Endpoint Raiz ---
@app.get("/")
def root():
    return {
        "mensagem": "API de Agendamento Multi-Tenant (Versão Modular)",
        "versao": "3.0.0",
        "arquitetura": "modular",
        "routers": [
            "admin", "auth", "profissionais", "agendamentos", 
            "pacientes", "medicos", "interacoes", "notifications", "utilitarios"
        ]
    }

# --- Servir Arquivos Estáticos ---
@app.get("/uploads/profiles/{filename}", tags=["Arquivos"])
def get_profile_image(filename: str):
    """Serve as imagens de perfil salvas localmente."""
    file_path = os.path.join("uploads", "profiles", filename)
    if os.path.exists(file_path):
        return FileResponse(file_path)
    else:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Imagem não encontrada")

@app.get("/uploads/fotos/{filename}", tags=["Arquivos"])
def get_foto(filename: str):
    """Serve fotos gerais salvas localmente."""
    file_path = os.path.join("uploads", "fotos", filename)
    if os.path.exists(file_path):
        return FileResponse(file_path)
    else:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Foto não encontrada")

@app.get("/uploads/relatorios/{filename}", tags=["Arquivos"])
def get_relatorio_photo(filename: str):
    """Serve fotos de relatórios médicos."""
    file_path = os.path.join("uploads", "relatorios", filename)
    if os.path.exists(file_path):
        return FileResponse(file_path)
    else:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Foto do relatório não encontrada")

@app.get("/uploads/arquivos/{filename}", tags=["Arquivos"])
def get_arquivo(filename: str):
    """Serve arquivos gerais salvos localmente."""
    file_path = os.path.join("uploads", "arquivos", filename)
    if os.path.exists(file_path):
        return FileResponse(file_path)
    else:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")

# --- Incluir Routers ---

# Administração da Plataforma e Gestão do Negócio
app.include_router(admin.platform_admin_router)
app.include_router(admin.business_admin_router)

# Autenticação e Usuários
app.include_router(auth.router)

# Profissionais
app.include_router(profissionais.public_router)
app.include_router(profissionais.self_management_router)

# Agendamentos
app.include_router(agendamentos.router)
app.include_router(agendamentos.professional_router)

# Pacientes, Fichas e Anamneses
app.include_router(pacientes.router)

# Médicos e Relatórios Médicos
app.include_router(medicos.router)

# Interações Sociais (Feed, Comentários, Avaliações)
app.include_router(interacoes.router)

# Notificações
app.include_router(notifications.router)

# Utilitários (Uploads, Pesquisas, etc.)
app.include_router(utilitarios.router)

# Serviços e Horários
app.include_router(servicos.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)