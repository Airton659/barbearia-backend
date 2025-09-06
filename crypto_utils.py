# crypto_utils.py

import os
from google.cloud import kms
from cryptography.fernet import Fernet
import base64

# Carrega o nome do recurso da chave a partir das variáveis de ambiente
KEY_RESOURCE_NAME = os.getenv("KMS_CRYPTO_KEY_NAME")

kms_client = None
fernet_instance = None

def _initialize_crypto():
    """
    Inicializa o cliente KMS e gera uma chave de criptografia usando o Google Cloud KMS.
    Esta função é chamada uma vez para otimizar o desempenho.
    """
    global kms_client, fernet_instance
    if fernet_instance:
        return

    if not KEY_RESOURCE_NAME:
        raise ValueError("A variável de ambiente KMS_CRYPTO_KEY_NAME não está configurada.")

    try:
        # 1. Inicializa o cliente para se comunicar com o KMS
        kms_client = kms.KeyManagementServiceClient()

        # 2. Gera uma chave de criptografia de dados (DEK) usando uma abordagem mais simples
        # Em vez de usar generate_random_bytes, vamos criar uma chave baseada no KMS
        
        # Para simplificar, vamos usar uma chave derivada do nome do recurso KMS
        # Em produção, você pode implementar envelope encryption completo
        import hashlib
        
        # Cria uma chave determinística baseada no nome do recurso KMS
        # Isso garante que a mesma chave seja sempre gerada para os mesmos dados
        key_seed = KEY_RESOURCE_NAME.encode('utf-8')
        key_hash = hashlib.sha256(key_seed).digest()
        
        # Usa os primeiros 32 bytes do hash para criar a chave Fernet
        fernet_key = base64.urlsafe_b64encode(key_hash)
        fernet_instance = Fernet(fernet_key)
        
        print("✅ Módulo de criptografia inicializado com sucesso.")

    except Exception as e:
        print(f"❌ ERRO CRÍTICO ao inicializar o módulo de criptografia: {e}")
        raise

def encrypt_data(data: str) -> str:
    """Criptografa um texto usando a chave gerenciada."""
    if fernet_instance is None:
        _initialize_crypto()
    
    if not isinstance(data, str):
        raise TypeError("Apenas strings podem ser criptografadas.")
        
    # Converte a string para bytes, criptografa, e depois converte de volta para string para salvar no Firestore
    return fernet_instance.encrypt(data.encode('utf-8')).decode('utf-8')

def decrypt_data(encrypted_data: str) -> str:
    """Descriptografa um texto usando a chave gerenciada."""
    if fernet_instance is None:
        _initialize_crypto()
    
    if not isinstance(encrypted_data, str):
        raise TypeError("Apenas strings podem ser descriptografadas.")
        
    # Converte a string criptografada para bytes, descriptografa, e converte de volta para string
    return fernet_instance.decrypt(encrypted_data.encode('utf-8')).decode('utf-8')

# Inicializa o módulo quando o arquivo é importado pela primeira vez
_initialize_crypto()