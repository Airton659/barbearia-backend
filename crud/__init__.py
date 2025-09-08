# crud/__init__.py
"""
Módulo CRUD organizado por domínios de negócio.
"""

# Utilitários
from crud.utils import (
    encrypt_user_sensitive_fields,
    decrypt_user_sensitive_fields,
    encrypt_endereco_fields,
    decrypt_endereco_fields,
    validate_phone_number,
    validate_cep,
    add_timestamps,
    processar_imagem_base64
)

# Usuários e Autenticação
from crud.usuarios import (
    buscar_usuario_por_firebase_uid,
    criar_ou_atualizar_usuario,
    adicionar_fcm_token,
    remover_fcm_token,
    atualizar_perfil_usuario
)

# Negócios
from crud.negocios import (
    admin_criar_negocio,
    admin_listar_negocios,
    buscar_negocio_por_id,
    atualizar_negocio
)

# Administração
from crud.admin import (
    check_admin_status,
    admin_listar_usuarios_por_negocio,
    admin_set_usuario_status,
    admin_atualizar_role_usuario,
    admin_criar_paciente,
    admin_listar_clientes_por_negocio
)

# Profissionais
from crud.profissionais import (
    buscar_profissional_por_uid,
    criar_profissional,
    listar_profissionais_por_negocio,
    buscar_profissional_por_id,
    atualizar_perfil_profissional,
    criar_servico,
    listar_servicos_por_profissional,
    atualizar_servico,
    deletar_servico
)

# Médicos
from crud.medicos import (
    criar_medico,
    listar_medicos_por_negocio,
    criar_relatorio_medico,
    listar_relatorios_por_paciente,
    listar_relatorios_pendentes_medico,
    atualizar_relatorio_medico,
    listar_historico_relatorios_medico
)

# Pacientes
from crud.pacientes import (
    listar_pacientes_por_profissional_ou_tecnico,
    atualizar_dados_pessoais_paciente,
    atualizar_endereco_paciente,
    atualizar_consentimento_lgpd
)

# Agendamentos
from crud.agendamentos import (
    criar_agendamento,
    listar_agendamentos_por_cliente,
    listar_agendamentos_por_profissional,
    atualizar_agendamento,
    cancelar_agendamento,
    listar_horarios_trabalho,
    criar_bloqueio,
    deletar_bloqueio
)

# Anamneses e Consultas
from crud.anamneses import (
    criar_anamnese,
    listar_anamneses_por_paciente,
    atualizar_anamnese,
    criar_consulta,
    criar_orientacao,
    listar_consultas,
    listar_orientacoes,
    listar_exames,
    listar_medicacoes,
    listar_checklist
)

# TODO: Importar quando criarmos
# from .notifications import *

# Migração completa - crud.py original não é mais necessário

__all__ = [
    # Utilitários
    'encrypt_user_sensitive_fields',
    'decrypt_user_sensitive_fields', 
    'encrypt_endereco_fields',
    'decrypt_endereco_fields',
    'validate_phone_number',
    'validate_cep',
    'add_timestamps',
    'processar_imagem_base64',
    
    # Usuários
    'buscar_usuario_por_firebase_uid',
    'criar_ou_atualizar_usuario',
    'adicionar_fcm_token',
    'remover_fcm_token',
    'atualizar_perfil_usuario',
    
    # Negócios
    'admin_criar_negocio',
    'admin_listar_negocios',
    'buscar_negocio_por_id',
    'atualizar_negocio',
    
    # Administração
    'check_admin_status',
    'admin_listar_usuarios_por_negocio',
    'admin_set_usuario_status',
    'admin_atualizar_role_usuario',
    'admin_criar_paciente',
    'admin_listar_clientes_por_negocio',
    
    # Profissionais
    'buscar_profissional_por_uid',
    'criar_profissional',
    'listar_profissionais_por_negocio',
    'buscar_profissional_por_id',
    'atualizar_perfil_profissional',
    'criar_servico',
    'listar_servicos_por_profissional',
    'atualizar_servico',
    'deletar_servico',
    
    # Médicos
    'criar_medico',
    'listar_medicos_por_negocio',
    'criar_relatorio_medico',
    'listar_relatorios_por_paciente',
    'listar_relatorios_pendentes_medico',
    'atualizar_relatorio_medico',
    'listar_historico_relatorios_medico',
    
    # Pacientes
    'listar_pacientes_por_profissional_ou_tecnico',
    'atualizar_dados_pessoais_paciente',
    'atualizar_endereco_paciente',
    'atualizar_consentimento_lgpd',
    
    # Agendamentos
    'criar_agendamento',
    'listar_agendamentos_por_cliente',
    'listar_agendamentos_por_profissional',
    'atualizar_agendamento',
    'cancelar_agendamento',
    'listar_horarios_trabalho',
    'criar_bloqueio',
    'deletar_bloqueio',
    
    # Anamneses e Consultas
    'criar_anamnese',
    'listar_anamneses_por_paciente',
    'atualizar_anamnese',
    'criar_consulta',
    'criar_orientacao',
    'listar_consultas',
    'listar_orientacoes',
    'listar_exames',
    'listar_medicacoes',
    'listar_checklist'
    
    # TODO: Adicionar exports das outras seções conforme criamos
]