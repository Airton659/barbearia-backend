# routers/__init__.py
"""
Routers modulares para a API FastAPI
"""

# Importar todos os routers para facilitar o uso
from . import admin
from . import auth  
from . import profissionais
from . import agendamentos
from . import pacientes
from . import medicos
from . import interacoes
from . import notifications
from . import utilitarios

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