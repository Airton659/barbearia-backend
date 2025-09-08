# routers/__init__.py
"""
Routers modulares para a API FastAPI
"""

# Importar todos os routers para facilitar o uso
from routers import admin
from routers import auth  
from routers import profissionais
from routers import agendamentos
from routers import pacientes
from routers import medicos
from routers import interacoes
from routers import notifications
from routers import utilitarios

__all__ = [
    'admin',
    'auth',
    'profissionais', 
    'agendamentos',
    'pacientes',
    'medicos',
    'interacoes',
    'notifications',
    'utilitarios'
]