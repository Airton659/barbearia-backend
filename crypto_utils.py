# crypto_utils.py

import os
from google.cloud import kms
from cryptography.fernet import Fernet
import base64

# Carrega o nome do recurso da chave a partir das variáveis de ambiente
# Vamos configurar isso no cloudbuild.yaml depois
KEY_RESOURCE_NAME = os.getenv("KMS_CRYPTO_KEY_NAME")

kms_client = None
fernet_instance = None

def _initialize_crypto():
    """
    Inicializa o cliente KMS e busca a chave de criptografia para criar uma instância do Fernet.
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

        # 2. Pede ao KMS para criar uma nova chave de criptografia de dados (DEK)
        # A chave principal (KEK) no KMS nunca sai do Google, ela apenas criptografa esta chave que usaremos.
        response = kms_client.generate_random_bytes(
            request={"location": "/".join(KEY_RESOURCE_NAME.split("/")[0:4]), "length_bytes": 32}
        )
        
        # 3. A chave que usaremos para criptografar os dados
        data_encryption_key = response.data

        # 4. Cria a instância do Fernet, que fará a criptografia simétrica
        fernet_instance = Fernet(base64.urlsafe_b64encode(data_encryption_key))
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