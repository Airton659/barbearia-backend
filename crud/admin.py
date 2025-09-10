# crud/admin.py
"""
CRUD para funções administrativas
"""

import logging
from typing import Optional, List, Dict
from firebase_admin import firestore, auth
import schemas
from crypto_utils import decrypt_data
from crud.profissionais import buscar_profissional_por_uid, criar_profissional
from crud.helpers import criar_log_auditoria
from crud.usuarios import criar_ou_atualizar_usuario
from crud.pacientes import atualizar_endereco_paciente
from crud.utils import (
    decrypt_user_sensitive_fields,
    encrypt_user_sensitive_fields,
    add_timestamps
)

logger = logging.getLogger(__name__)

# Campos sensíveis que precisam de criptografia
USER_SENSITIVE_FIELDS = ['nome', 'telefone']


def check_admin_status(db: firestore.client, negocio_id: str) -> bool:
    """Verifica se o negócio já tem um admin."""
    try:
        negocio_doc = db.collection('negocios').document(negocio_id).get()
        return negocio_doc.exists and negocio_doc.to_dict().get("admin_uid") is not None
    except Exception as e:
        logger.error(f"Erro ao verificar o status do admin para o negócio {negocio_id}: {e}")
        return False


def admin_listar_usuarios_por_negocio(db: firestore.client, negocio_id: str, status: str = 'ativo') -> List[Dict]:
    """
    Lista todos os usuários de um negócio, com filtro de status.
    VERSÃO FINAL: Retorna o campo de status corretamente para cada usuário.
    """
    usuarios = []
    try:
        query = db.collection('usuarios').where(f'roles.{negocio_id}', 'in', ['cliente', 'profissional', 'admin', 'tecnico', 'medico'])

        for doc in query.stream():
            usuario_data = doc.to_dict()
            
            # Pega o status do usuário para o negócio específico, com 'ativo' como padrão.
            status_no_negocio = usuario_data.get('status_por_negocio', {}).get(negocio_id, 'ativo')
            
            # LÓGICA DE FILTRO (continua a mesma)
            deve_incluir = False
            if status == 'all':
                deve_incluir = True
            elif status_no_negocio == status:
                deve_incluir = True

            if deve_incluir:
                usuario_data['id'] = doc.id
                
                # Descriptografa campos sensíveis do usuário
                if 'nome' in usuario_data and usuario_data['nome']:
                    try:
                        usuario_data['nome'] = decrypt_data(usuario_data['nome'])
                    except Exception as e:
                        logger.error(f"Erro ao descriptografar nome do usuário {doc.id}: {e}")
                        usuario_data['nome'] = "[Erro na descriptografia]"
                
                if 'telefone' in usuario_data and usuario_data['telefone']:
                    try:
                        usuario_data['telefone'] = decrypt_data(usuario_data['telefone'])
                    except Exception as e:
                        logger.error(f"Erro ao descriptografar telefone do usuário {doc.id}: {e}")
                        usuario_data['telefone'] = "[Erro na descriptografia]"
                
                if 'endereco' in usuario_data and usuario_data['endereco']:
                    endereco_descriptografado = {}
                    for key, value in usuario_data['endereco'].items():
                        if value and isinstance(value, str) and value.strip():
                            try:
                                endereco_descriptografado[key] = decrypt_data(value)
                            except Exception as e:
                                logger.error(f"Erro ao descriptografar campo de endereço {key} do usuário {doc.id}: {e}")
                                endereco_descriptografado[key] = "[Erro na descriptografia]"
                        else:
                            endereco_descriptografado[key] = value
                    usuario_data['endereco'] = endereco_descriptografado
                
                # ***** A CORREÇÃO ESTÁ AQUI *****
                # Adiciona o status do negócio ao dicionário de resposta.
                # O nome do campo foi corrigido no schema para 'status_por_negocio' para ser mais claro.
                # Esta linha garante que o dado seja populado na resposta da API.
                usuario_data['status_por_negocio'] = {negocio_id: status_no_negocio}

                # A lógica de enriquecimento de dados continua a mesma...
                user_role = usuario_data.get("roles", {}).get(negocio_id)
                if user_role in ['profissional', 'admin']:
                    firebase_uid = usuario_data.get('firebase_uid')
                    if firebase_uid:
                        perfil_profissional = buscar_profissional_por_uid(db, negocio_id, firebase_uid)
                        usuario_data['profissional_id'] = perfil_profissional.get('id') if perfil_profissional else None
                elif user_role == 'cliente':
                    enfermeiro_user_id = usuario_data.get('enfermeiro_id')
                    if enfermeiro_user_id:
                        enfermeiro_doc = db.collection('usuarios').document(enfermeiro_user_id).get()
                        if enfermeiro_doc.exists:
                            firebase_uid_enfermeiro = enfermeiro_doc.to_dict().get('firebase_uid')
                            perfil_enfermeiro = buscar_profissional_por_uid(db, negocio_id, firebase_uid_enfermeiro)
                            usuario_data['enfermeiro_vinculado_id'] = perfil_enfermeiro.get('id') if perfil_enfermeiro else None
                    usuario_data['tecnicos_vinculados_ids'] = usuario_data.get('tecnicos_ids', [])

                usuarios.append(usuario_data)

        return usuarios
    except Exception as e:
        logger.error(f"Erro ao listar usuários para o negocio_id {negocio_id}: {e}")
        return []


def admin_set_usuario_status(db: firestore.client, negocio_id: str, user_id: str, status: str, autor_uid: str) -> Optional[Dict]:
    """Define o status de um usuário ('ativo' ou 'inativo') em um negócio."""
    if status not in ['ativo', 'inativo']:
        raise ValueError("Status inválido. Use 'ativo' ou 'inativo'.")

    user_ref = db.collection('usuarios').document(user_id)
    status_path = f'status_por_negocio.{negocio_id}'
    user_ref.update({status_path: status})

    criar_log_auditoria(
        db,
        acao=f"USUARIO_STATUS_{status.upper()}",
        usuario_id=autor_uid,
        detalhes={
            "negocio_id": negocio_id,
            "usuario_alvo_id": user_id
        }
    )
    logger.info(f"Status do usuário {user_id} definido como '{status}' no negócio {negocio_id}.")

    doc = user_ref.get()
    if doc.exists:
        data = doc.to_dict()
        data['id'] = doc.id
        
        # Descriptografa campos sensíveis do usuário
        if 'nome' in data and data['nome']:
            try:
                data['nome'] = decrypt_data(data['nome'])
            except Exception as e:
                logger.error(f"Erro ao descriptografar nome do usuário {doc.id}: {e}")
                data['nome'] = "[Erro na descriptografia]"
        
        if 'telefone' in data and data['telefone']:
            try:
                data['telefone'] = decrypt_data(data['telefone'])
            except Exception as e:
                logger.error(f"Erro ao descriptografar telefone do usuário {doc.id}: {e}")
                data['telefone'] = "[Erro na descriptografia]"
        
        if 'endereco' in data and data['endereco']:
            endereco_descriptografado = {}
            for key, value in data['endereco'].items():
                if value and isinstance(value, str) and value.strip():
                    try:
                        endereco_descriptografado[key] = decrypt_data(value)
                    except Exception as e:
                        logger.error(f"Erro ao descriptografar campo de endereço {key} do usuário {doc.id}: {e}")
                        endereco_descriptografado[key] = "[Erro na descriptografia]"
                else:
                    endereco_descriptografado[key] = value
            data['endereco'] = endereco_descriptografado
        
        return data
    return None


def admin_atualizar_role_usuario(db: firestore.client, negocio_id: str, user_id: str, novo_role: str, autor_uid: str) -> Optional[Dict]:
    """
    Atualiza a role de um usuário dentro de um negócio específico.
    Cria/desativa o perfil profissional conforme necessário.
    """
    # --- ALTERAÇÃO AQUI: Adicionando 'medico' à lista de roles válidas ---
    if novo_role not in ['cliente', 'profissional', 'admin', 'tecnico', 'medico']:
        raise ValueError("Role inválida. As roles permitidas são 'cliente', 'profissional', 'admin', 'tecnico' e 'medico'.")
    # --- FIM DA ALTERAÇÃO ---

    user_ref = db.collection('usuarios').document(user_id)
    user_doc = user_ref.get()

    if not user_doc.exists:
        logger.warning(f"Tentativa de atualizar role de usuário inexistente com ID: {user_id}")
        return None

    user_data = user_doc.to_dict()

    # Verifica se o usuário pertence ao negócio
    if negocio_id not in user_data.get("roles", {}):
        logger.warning(f"Usuário {user_id} não pertence ao negócio {negocio_id}.")
        return None

    role_antiga = user_data.get("roles", {}).get(negocio_id)

    role_path = f'roles.{negocio_id}'
    user_ref.update({role_path: novo_role})

    criar_log_auditoria(
        db,
        acao="ROLE_UPDATE",
        usuario_id=autor_uid,
        detalhes={
            "negocio_id": negocio_id,
            "usuario_alvo_id": user_id, 
            "role_antiga": role_antiga, 
            "nova_role": novo_role
        }
    )

    # Lógica para perfil profissional
    perfil_profissional = buscar_profissional_por_uid(db, negocio_id, user_data['firebase_uid'])

    if novo_role == 'profissional' or novo_role == 'admin':
        if not perfil_profissional:
            # Cria o perfil profissional se não existir
            novo_profissional_data = schemas.ProfissionalCreate(
                negocio_id=negocio_id,
                usuario_uid=user_data['firebase_uid'],
                nome=user_data.get('nome', 'Profissional sem nome'),
                ativo=True,
                fotos={}
            )
            criar_profissional(db, novo_profissional_data)
            logger.info(f"Perfil profissional criado para o usuário {user_data['email']} no negócio {negocio_id}.")
        elif not perfil_profissional.get('ativo'):
            # Reativa o perfil se já existir e estiver inativo
            prof_ref = db.collection('profissionais').document(perfil_profissional['id'])
            prof_ref.update({"ativo": True})
            logger.info(f"Perfil profissional reativado para o usuário {user_data['email']} no negócio {negocio_id}.")

    elif novo_role == 'cliente' or novo_role == 'tecnico' or novo_role == 'medico': # Desativa perfil se virar cliente, tecnico ou medico
        if perfil_profissional and perfil_profissional.get('ativo'):
            # Desativa o perfil profissional se existir e estiver ativo
            prof_ref = db.collection('profissionais').document(perfil_profissional['id'])
            prof_ref.update({"ativo": False})
            logger.info(f"Perfil profissional desativado para o usuário {user_data['email']} no negócio {negocio_id}.")

    logger.info(f"Role do usuário {user_data['email']} atualizada para '{novo_role}' no negócio {negocio_id}.")

    updated_user_doc = user_ref.get()
    updated_user_data = updated_user_doc.to_dict()
    updated_user_data['id'] = updated_user_doc.id
    
    # Descriptografa campos sensíveis do usuário
    if 'nome' in updated_user_data and updated_user_data['nome']:
        try:
            updated_user_data['nome'] = decrypt_data(updated_user_data['nome'])
        except Exception as e:
            logger.error(f"Erro ao descriptografar nome do usuário {updated_user_doc.id}: {e}")
            updated_user_data['nome'] = "[Erro na descriptografia]"
    
    if 'telefone' in updated_user_data and updated_user_data['telefone']:
        try:
            updated_user_data['telefone'] = decrypt_data(updated_user_data['telefone'])
        except Exception as e:
            logger.error(f"Erro ao descriptografar telefone do usuário {updated_user_doc.id}: {e}")
            updated_user_data['telefone'] = "[Erro na descriptografia]"
    
    if 'endereco' in updated_user_data and updated_user_data['endereco']:
        endereco_descriptografado = {}
        for key, value in updated_user_data['endereco'].items():
            if value and isinstance(value, str) and value.strip():
                try:
                    endereco_descriptografado[key] = decrypt_data(value)
                except Exception as e:
                    logger.error(f"Erro ao descriptografar campo de endereço {key} do usuário {updated_user_doc.id}: {e}")
                    endereco_descriptografado[key] = "[Erro na descriptografia]"
            else:
                endereco_descriptografado[key] = value
        updated_user_data['endereco'] = endereco_descriptografado
    
    return updated_user_data


def admin_criar_paciente(db: firestore.client, negocio_id: str, paciente_data: schemas.PacienteCreateByAdmin) -> Dict:
    """
    (Admin ou Enfermeiro) Cria um novo usuário de paciente no Firebase Auth e o sincroniza no Firestore,
    lidando corretamente com o endereço como um campo exclusivo do paciente.
    """
    # 1. Criar usuário no Firebase Auth (lógica inalterada)
    try:
        firebase_user = auth.create_user(
            email=paciente_data.email,
            password=paciente_data.password,
            display_name=paciente_data.nome,
            email_verified=False
        )
        logger.info(f"Usuário paciente criado no Firebase Auth com UID: {firebase_user.uid}")
    except auth.EmailAlreadyExistsError:
        raise ValueError(f"O e-mail {paciente_data.email} já está em uso.")
    except Exception as e:
        logger.error(f"Erro ao criar usuário paciente no Firebase Auth: {e}")
        raise

    # 2. Sincronizar o usuário no Firestore, SEM o endereço.
    # O schema UsuarioSync não tem mais o campo 'endereco'.
    sync_data = schemas.UsuarioSync(
        nome=paciente_data.nome,
        email=paciente_data.email,
        firebase_uid=firebase_user.uid,
        negocio_id=negocio_id,
        telefone=paciente_data.telefone
    )

    try:
        # Cria o perfil básico do usuário (sem endereço)
        user_profile = criar_ou_atualizar_usuario(db, sync_data)
        
        # 3. Se um endereço foi fornecido na requisição, ATUALIZA o documento recém-criado
        if paciente_data.endereco:
            logger.info(f"Adicionando endereço ao paciente recém-criado: {user_profile['id']}")
            # Chama a função específica para adicionar/atualizar o endereço
            atualizar_endereco_paciente(db, user_profile['id'], paciente_data.endereco)
            # Adiciona o endereço ao dicionário de resposta para consistência
            user_profile['endereco'] = paciente_data.endereco.model_dump()
        
        # 4. Adicionar dados pessoais básicos se fornecidos
        dados_pessoais_update = {}
        if paciente_data.data_nascimento:
            dados_pessoais_update['data_nascimento'] = paciente_data.data_nascimento
        if paciente_data.sexo:
            dados_pessoais_update['sexo'] = paciente_data.sexo
        if paciente_data.estado_civil:
            dados_pessoais_update['estado_civil'] = paciente_data.estado_civil
        if paciente_data.profissao:
            dados_pessoais_update['profissao'] = paciente_data.profissao
            
        if dados_pessoais_update:
            logger.info(f"Adicionando dados pessoais ao paciente recém-criado: {user_profile['id']}")
            # Atualizar documento com dados pessoais
            user_ref = db.collection('usuarios').document(user_profile['id'])
            user_ref.update(dados_pessoais_update)
            # Adicionar aos dados de resposta
            user_profile.update(dados_pessoais_update)

        logger.info(f"Perfil do paciente {paciente_data.email} sincronizado com sucesso no Firestore.")
        return user_profile

    except Exception as e:
        # A lógica de reversão em caso de erro continua a mesma
        logger.error(f"Erro ao sincronizar paciente no Firestore. Tentando reverter a criação no Auth... UID: {firebase_user.uid}")
        try:
            auth.delete_user(firebase_user.uid)
            logger.info(f"Reversão bem-sucedida: usuário {firebase_user.uid} deletado do Auth.")
        except Exception as delete_e:
            logger.critical(f"FALHA CRÍTICA NA REVERSÃO: não foi possível deletar o usuário {firebase_user.uid} do Auth. {delete_e}")
        raise e


def admin_listar_clientes_por_negocio(db: firestore.client, negocio_id: str, status: str = 'ativo') -> List[Dict]:
    """Lista todos os clientes de um negócio específico."""
    clientes = []
    try:
        query = db.collection('usuarios').where(f'roles.{negocio_id}', '==', 'cliente')
        
        for doc in query.stream():
            cliente_data = doc.to_dict()
            
            # Verificar status
            status_por_negocio = cliente_data.get('status_por_negocio', {})
            user_status = status_por_negocio.get(negocio_id, 'ativo')
            
            if user_status == status:
                cliente_data['id'] = doc.id
                
                # Descriptografar campos sensíveis
                cliente_data = decrypt_user_sensitive_fields(cliente_data, USER_SENSITIVE_FIELDS)
                
                # Descriptografar endereço se existir
                if 'endereco' in cliente_data and cliente_data['endereco']:
                    endereco_descriptografado = {}
                    for key, value in cliente_data['endereco'].items():
                        if value and isinstance(value, str) and value.strip():
                            try:
                                endereco_descriptografado[key] = decrypt_data(value)
                            except Exception as e:
                                logger.error(f"Erro ao descriptografar campo de endereço {key} do cliente {doc.id}: {e}")
                                endereco_descriptografado[key] = "[Erro na descriptografia]"
                        else:
                            endereco_descriptografado[key] = value
                    cliente_data['endereco'] = endereco_descriptografado
                
                clientes.append(cliente_data)
        
        logger.info(f"Retornando {len(clientes)} clientes para o negócio {negocio_id} com status {status}")
        return clientes
    except Exception as e:
        logger.error(f"Erro ao listar clientes do negócio {negocio_id}: {e}")
        return []


def admin_promover_cliente_para_profissional(db: firestore.client, negocio_id: str, cliente_uid: str) -> Optional[Dict]:
    """Promove um usuário de 'cliente' para 'profissional' e cria seu perfil profissional."""
    from .usuarios import buscar_usuario_por_firebase_uid
    from .profissionais import criar_profissional
    
    try:
        user_doc = buscar_usuario_por_firebase_uid(db, cliente_uid)
        if not user_doc:
            logger.warning(f"Tentativa de promover usuário inexistente com UID: {cliente_uid}")
            return None

        if user_doc.get("roles", {}).get(negocio_id) == 'cliente':
            # 1. Atualiza a permissão do usuário
            user_ref = db.collection('usuarios').document(user_doc['id'])
            user_ref.update({
                f'roles.{negocio_id}': 'profissional'
            })
            
            # 2. Cria o perfil profissional básico
            novo_profissional_data = schemas.ProfissionalCreate(
                negocio_id=negocio_id,
                usuario_uid=cliente_uid,
                nome=user_doc.get('nome', 'Profissional sem nome'),
                especialidades="A definir",
                ativo=True,
                fotos={}
            )
            criar_profissional(db, novo_profissional_data)
            
            logger.info(f"Usuário {user_doc['email']} promovido para profissional no negócio {negocio_id}.")
            
            # Retorna os dados atualizados do usuário
            return buscar_usuario_por_firebase_uid(db, cliente_uid)
        else:
            logger.warning(f"Usuário {user_doc.get('email')} não é um cliente deste negócio e não pode ser promovido.")
            return None
    except Exception as e:
        logger.error(f"Erro ao promover cliente {cliente_uid} para profissional: {e}")
        return None


def admin_rebaixar_profissional_para_cliente(db: firestore.client, negocio_id: str, profissional_uid: str) -> Optional[Dict]:
    """Rebaixa um usuário de 'profissional' para 'cliente' e desativa seu perfil profissional."""
    from .usuarios import buscar_usuario_por_firebase_uid
    
    try:
        user_doc = buscar_usuario_por_firebase_uid(db, profissional_uid)
        if not user_doc:
            logger.warning(f"Tentativa de rebaixar usuário inexistente com UID: {profissional_uid}")
            return None

        if user_doc.get("roles", {}).get(negocio_id) == 'profissional':
            # 1. Atualiza a permissão do usuário
            user_ref = db.collection('usuarios').document(user_doc['id'])
            user_ref.update({
                f'roles.{negocio_id}': 'cliente'
            })
            
            # 2. Desativa o perfil profissional
            profissional_query = db.collection('profissionais') \
                .where('usuario_uid', '==', profissional_uid) \
                .where('negocio_id', '==', negocio_id)
            
            for doc in profissional_query.stream():
                doc.reference.update({'ativo': False})
            
            logger.info(f"Usuário {user_doc['email']} rebaixado para cliente no negócio {negocio_id}.")
            
            # Retorna os dados atualizados do usuário
            return buscar_usuario_por_firebase_uid(db, profissional_uid)
        else:
            logger.warning(f"Usuário {user_doc.get('email')} não é um profissional deste negócio e não pode ser rebaixado.")
            return None
    except Exception as e:
        logger.error(f"Erro ao rebaixar profissional {profissional_uid} para cliente: {e}")
        return None