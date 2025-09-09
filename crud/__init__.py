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

# Importar decrypt_data da crypto_utils via utils
from crypto_utils import decrypt_data

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
    admin_listar_clientes_por_negocio,
    admin_promover_cliente_para_profissional,
    admin_rebaixar_profissional_para_cliente
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
    listar_historico_relatorios_medico,
    update_medico,
    delete_medico,
    adicionar_foto_relatorio,
    aprovar_relatorio,
    recusar_relatorio
)

# Pacientes
from crud.pacientes import (
    listar_pacientes_por_profissional_ou_tecnico,
    atualizar_dados_pessoais_paciente,
    atualizar_endereco_paciente,
    atualizar_consentimento_lgpd,
    get_ficha_completa_paciente
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
    deletar_bloqueio,
    cancelar_agendamento_pelo_profissional,
    definir_horarios_trabalho
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
    listar_checklist,
    criar_exame,
    update_exame,
    delete_exame,
    criar_medicacao,
    criar_checklist_item
)

# Notificações
from crud.notifications import (
    _send_data_push_to_tokens,
    listar_notificacoes,
    contar_notificacoes_nao_lidas,
    marcar_notificacao_como_lida,
    marcar_todas_como_lidas,
    agendar_notificacao,
    _notificar_cliente_cancelamento
)

# Checklist Diário
from crud.checklist_diario import (
    criar_registro_diario,
    listar_registros_diario,
    update_registro_diario,
    delete_registro_diario,
    adicionar_registro_diario,
    listar_checklist_diario,
    atualizar_item_checklist_diario,
    listar_checklist_diario_com_replicacao,
    get_checklist_diario_plano_ativo,
    criar_registro_diario_estruturado,
    listar_registros_diario_estruturado,
    atualizar_registro_diario_estruturado,
    deletar_registro_diario_estruturado
)

# Feed e Postagens
from crud.feed import (
    criar_postagem,
    listar_postagens_por_profissional,
    listar_feed_por_negocio,
    toggle_curtida,
    criar_comentario,
    listar_comentarios,
    deletar_postagem,
    deletar_comentario
)

# Funções Auxiliares
from crud.auxiliary import (
    calcular_horarios_disponiveis,
    criar_avaliacao,
    listar_avaliacoes_por_profissional,
    vincular_paciente_enfermeiro,
    desvincular_paciente_enfermeiro,
    vincular_paciente_medico,
    vincular_tecnicos_paciente,
    vincular_supervisor_tecnico,
    enviar_pesquisa_satisfacao,
    submeter_respostas_pesquisa,
    listar_pesquisas_por_paciente,
    listar_resultados_pesquisas
)

# Funções Auxiliares Internas
from crud.helpers import (
    _delete_subcollection_item,
    _update_subcollection_item,
    _dedup_checklist_items,
    _detectar_tipo_conteudo,
    adicionar_exame,
    adicionar_item_checklist,
    delete_checklist_item,
    update_checklist_item,
    update_consulta,
    delete_consulta,
    update_medicacao,
    delete_medicacao,
    update_orientacao,
    delete_orientacao,
    prescrever_medicacao,
    criar_log_auditoria,
    registrar_confirmacao_leitura_plano,
    verificar_leitura_plano_do_dia
)

# Suporte Psicológico
from crud.psicologico import (
    criar_suporte_psicologico,
    listar_suportes_psicologicos,
    atualizar_suporte_psicologico,
    deletar_suporte_psicologico,
    listar_tecnicos_supervisionados_por_paciente
)

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
    'decrypt_data',
    
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
    'admin_promover_cliente_para_profissional',
    'admin_rebaixar_profissional_para_cliente',
    
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
    'update_medico',
    'delete_medico',
    'adicionar_foto_relatorio',
    'aprovar_relatorio',
    'recusar_relatorio',
    
    # Pacientes
    'listar_pacientes_por_profissional_ou_tecnico',
    'atualizar_dados_pessoais_paciente',
    'atualizar_endereco_paciente',
    'atualizar_consentimento_lgpd',
    'get_ficha_completa_paciente',
    
    # Agendamentos
    'criar_agendamento',
    'listar_agendamentos_por_cliente',
    'listar_agendamentos_por_profissional',
    'atualizar_agendamento',
    'cancelar_agendamento',
    'listar_horarios_trabalho',
    'criar_bloqueio',
    'deletar_bloqueio',
    'cancelar_agendamento_pelo_profissional',
    'definir_horarios_trabalho',
    
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
    'listar_checklist',
    'criar_exame',
    'update_exame',
    'delete_exame',
    'criar_medicacao',
    'criar_checklist_item',
    
    # Notificações
    '_send_data_push_to_tokens',
    'listar_notificacoes',
    'contar_notificacoes_nao_lidas',
    'marcar_notificacao_como_lida',
    'marcar_todas_como_lidas',
    'agendar_notificacao',
    '_notificar_cliente_cancelamento',
    
    # Checklist Diário
    'criar_registro_diario',
    'listar_registros_diario',
    'update_registro_diario',
    'delete_registro_diario',
    'adicionar_registro_diario',
    'listar_checklist_diario',
    'atualizar_item_checklist_diario',
    'listar_checklist_diario_com_replicacao',
    'get_checklist_diario_plano_ativo',
    'criar_registro_diario_estruturado',
    'listar_registros_diario_estruturado',
    'atualizar_registro_diario_estruturado',
    'deletar_registro_diario_estruturado',
    
    # Feed e Postagens
    'criar_postagem',
    'listar_postagens_por_profissional',
    'listar_feed_por_negocio',
    'toggle_curtida',
    'criar_comentario',
    'listar_comentarios',
    'deletar_postagem',
    'deletar_comentario',
    
    # Funções Auxiliares
    'calcular_horarios_disponiveis',
    'criar_avaliacao',
    'listar_avaliacoes_por_profissional',
    'vincular_paciente_enfermeiro',
    'desvincular_paciente_enfermeiro',
    'vincular_paciente_medico',
    'vincular_tecnicos_paciente',
    'vincular_supervisor_tecnico',
    'enviar_pesquisa_satisfacao',
    'submeter_respostas_pesquisa',
    'listar_pesquisas_por_paciente',
    'listar_resultados_pesquisas',
    
    # Funções Auxiliares Internas
    '_delete_subcollection_item',
    '_update_subcollection_item',
    '_dedup_checklist_items',
    '_detectar_tipo_conteudo',
    'adicionar_exame',
    'adicionar_item_checklist',
    'delete_checklist_item',
    'update_checklist_item',
    'update_consulta',
    'delete_consulta',
    'update_medicacao',
    'delete_medicacao',
    'update_orientacao',
    'delete_orientacao',
    'prescrever_medicacao',
    'criar_log_auditoria',
    'registrar_confirmacao_leitura_plano',
    'verificar_leitura_plano_do_dia',
    
    # Suporte Psicológico
    'criar_suporte_psicologico',
    'listar_suportes_psicologicos',
    'atualizar_suporte_psicologico',
    'deletar_suporte_psicologico',
    'listar_tecnicos_supervisionados_por_paciente'
]