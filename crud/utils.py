# crud/utils.py
"""
Utilitários e funções auxiliares reutilizáveis
"""

import logging
from datetime import datetime
from typing import Optional, Dict
from firebase_admin import firestore
from crypto_utils import encrypt_data, decrypt_data

logger = logging.getLogger(__name__)

def encrypt_user_sensitive_fields(data: Dict, fields: list) -> Dict:
    """
    Criptografa campos sensíveis de um dicionário de dados do usuário.
    
    Args:
        data: Dicionário com dados do usuário
        fields: Lista de campos para criptografar
        
    Returns:
        Dicionário com campos criptografados
    """
    encrypted_data = data.copy()
    
    for field in fields:
        if field in encrypted_data and encrypted_data[field] is not None:
            if isinstance(encrypted_data[field], str) and encrypted_data[field].strip():
                encrypted_data[field] = encrypt_data(encrypted_data[field])
    
    return encrypted_data


def decrypt_user_sensitive_fields(data: Dict, fields: list) -> Dict:
    """
    Descriptografa campos sensíveis de um dicionário de dados do usuário.
    
    Args:
        data: Dicionário com dados criptografados
        fields: Lista de campos para descriptografar
        
    Returns:
        Dicionário com campos descriptografados
    """
    decrypted_data = data.copy()
    
    for field in fields:
        if field in decrypted_data and decrypted_data[field] is not None:
            if isinstance(decrypted_data[field], str) and decrypted_data[field].strip():
                try:
                    decrypted_data[field] = decrypt_data(decrypted_data[field])
                except Exception as e:
                    logger.error(f"Erro ao descriptografar campo {field}: {e}")
                    decrypted_data[field] = "[Erro na descriptografia]"
    
    return decrypted_data


def encrypt_endereco_fields(endereco: Dict) -> Dict:
    """
    Criptografa campos de endereço.
    
    Args:
        endereco: Dicionário com dados do endereço
        
    Returns:
        Dicionário com endereço criptografado
    """
    if not endereco:
        return endereco
        
    endereco_criptografado = {}
    for campo, valor in endereco.items():
        if valor and isinstance(valor, str) and valor.strip():
            endereco_criptografado[campo] = encrypt_data(valor.strip())
        else:
            endereco_criptografado[campo] = valor
    
    return endereco_criptografado


def decrypt_endereco_fields(endereco: Dict) -> Dict:
    """
    Descriptografa campos de endereço.
    
    Args:
        endereco: Dicionário com dados criptografados do endereço
        
    Returns:
        Dicionário com endereço descriptografado
    """
    if not endereco:
        return endereco
        
    endereco_descriptografado = {}
    for campo, valor in endereco.items():
        if valor and isinstance(valor, str) and valor.strip():
            try:
                endereco_descriptografado[campo] = decrypt_data(valor)
            except Exception as e:
                logger.error(f"Erro ao descriptografar campo {campo} do endereço: {e}")
                endereco_descriptografado[campo] = "[Erro na descriptografia]"
        else:
            endereco_descriptografado[campo] = valor
    
    return endereco_descriptografado


def validate_phone_number(telefone: str) -> bool:
    """
    Valida formato básico de telefone (DDD + número).
    
    Args:
        telefone: Número de telefone
        
    Returns:
        True se válido, False caso contrário
    """
    telefone_limpo = ''.join(filter(str.isdigit, telefone))
    return len(telefone_limpo) >= 10


def validate_cep(cep: str) -> bool:
    """
    Valida formato básico de CEP (8 dígitos).
    
    Args:
        cep: Código postal
        
    Returns:
        True se válido, False caso contrário
    """
    cep_limpo = ''.join(filter(str.isdigit, cep))
    return len(cep_limpo) == 8


def add_timestamps(data: Dict, is_update: bool = False) -> Dict:
    """
    Adiciona timestamps aos dados.
    
    Args:
        data: Dicionário de dados
        is_update: Se True, adiciona updated_at. Se False, adiciona created_at
        
    Returns:
        Dicionário com timestamps adicionados
    """
    data_with_timestamps = data.copy()
    
    if is_update:
        data_with_timestamps['updated_at'] = firestore.SERVER_TIMESTAMP
    else:
        data_with_timestamps['created_at'] = firestore.SERVER_TIMESTAMP
        data_with_timestamps['updated_at'] = None
    
    return data_with_timestamps


def processar_imagem_base64(base64_data: str, user_id: str) -> Optional[str]:
    """
    Processa imagem Base64 e salva localmente (implementação para desenvolvimento).
    
    Args:
        base64_data: Dados da imagem em Base64
        user_id: ID do usuário
        
    Returns:
        URL da imagem salva ou None se erro
    """
    try:
        import base64
        import os
        
        # Validar formato Base64
        if not base64_data.startswith('data:image/'):
            raise ValueError("Formato de imagem Base64 inválido")
        
        # Extrair tipo de imagem e dados
        header, encoded_data = base64_data.split(',', 1)
        image_type = header.split('/')[1].split(';')[0]
        
        if image_type not in ['jpeg', 'jpg', 'png']:
            raise ValueError("Tipo de imagem não suportado. Use JPEG ou PNG")
        
        # Decodificar Base64
        image_data = base64.b64decode(encoded_data)
        
        # Verificar tamanho (máximo 5MB)
        if len(image_data) > 5 * 1024 * 1024:
            raise ValueError("Imagem muito grande. Máximo 5MB")
        
        # Gerar nome único para o arquivo
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"profile_{user_id}_{timestamp}.{image_type}"
        
        # Criar diretório local para salvar as imagens (se não existir)
        upload_dir = "uploads/profiles"
        os.makedirs(upload_dir, exist_ok=True)
        
        # Salvar arquivo localmente
        file_path = os.path.join(upload_dir, filename)
        with open(file_path, 'wb') as f:
            f.write(image_data)
        
        # Retornar URL para servir a imagem
        # Em desenvolvimento, assumindo que há um servidor servindo /uploads/
        base_url = "https://barbearia-backend-service-862082955632.southamerica-east1.run.app"
        image_url = f"{base_url}/uploads/profiles/{filename}"
        
        logger.info(f"Imagem salva para usuário {user_id}: {file_path} -> {image_url}")
        return image_url
        
    except Exception as e:
        logger.error(f"Erro ao processar imagem Base64 para usuário {user_id}: {e}")
        return None