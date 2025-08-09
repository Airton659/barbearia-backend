# barbearia-backend/database.py (Versão para Firestore)

import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud import secretmanager
import json
import os

# Variável global para armazenar a instância do cliente do Firestore
db_client = None

def initialize_firebase_app():
    """
    Inicializa o Firebase Admin SDK usando credenciais do Google Secret Manager.
    Esta função deve ser chamada na inicialização da aplicação FastAPI.
    """
    global db_client
    # Evita reinicialização se o app recarregar (comum em desenvolvimento)
    if not firebase_admin._apps:
        try:
            print("Inicializando Firebase Admin SDK...")
            # ID do projeto e do segredo onde a chave de serviço está armazenada
            project_id = os.getenv("GCP_PROJECT_ID", "teste-notificacao-barbearia")
            secret_id = "firebase-admin-credentials"
            version_id = "latest"

            # Cria o cliente do Secret Manager
            client = secretmanager.SecretManagerServiceClient()

            # Monta o nome completo do recurso do segredo
            name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"

            # Acessa a versão mais recente do segredo
            response = client.access_secret_version(request={"name": name})

            # Decodifica o payload (o conteúdo do JSON da chave de serviço)
            payload = response.payload.data.decode("UTF-8")
            cred_json = json.loads(payload)

            # Inicializa o Firebase com as credenciais
            cred = credentials.Certificate(cred_json)
            firebase_admin.initialize_app(cred)
            
            print("Firebase Admin SDK inicializado com sucesso.")

        except Exception as e:
            print(f"ERRO CRÍTICO ao inicializar o Firebase via Secret Manager: {e}")
            # Levanta a exceção para impedir que a aplicação inicie sem o Firebase
            raise e

    # Inicializa o cliente do Firestore e o armazena na variável global
    db_client = firestore.client()
    print("Cliente do Firestore inicializado.")

def get_db():
    """
    Função de dependência do FastAPI para fornecer a instância do cliente do Firestore.
    Garante que a inicialização ocorreu antes de retornar o cliente.
    """
    if db_client is None:
        # Isso pode acontecer se a aplicação tentar acessar o DB antes do startup.
        # Uma inicialização robusta no evento de startup do FastAPI previne isso.
        raise Exception("Cliente do Firestore não foi inicializado. Chame initialize_firebase_app() no startup.")
    
    # Simplesmente retorna a instância do cliente já criada.
    # Não há necessidade de try/finally como nas sessões SQL.
    yield db_client