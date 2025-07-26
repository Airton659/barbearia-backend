import pytest
import httpx

API_URL = "https://barbearia-backend-dw3o.onrender.com"
# Define um timeout padrão para os testes, evitando erros no "cold start" do Render
DEFAULT_TIMEOUT = 30.0

@pytest.fixture(scope="session")
def base_url():
    return API_URL

@pytest.fixture(scope="session")
def user_payload():
    return {
        "nome": "Usuário Teste",
        "email": "usuario.teste@example.com",
        "senha": "teste123"
    }

@pytest.fixture(scope="session")
def login_token(user_payload, base_url):
    # Usamos um client para definir um timeout padrão para todas as requisições da fixture
    with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
        # Tenta criar o usuário. Não há problema se ele já existir (o endpoint retornará 400).
        client.post(f"{base_url}/usuarios", json=user_payload)

        # Faz o login para obter o token
        response = client.post(
            f"{base_url}/login",
            data={
                "username": user_payload["email"],
                "password": user_payload["senha"]
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        # Lança uma exceção se o login falhar, o que interrompe os testes com uma mensagem clara.
        response.raise_for_status() 
        
        token_data = response.json()
        
        # Garante que a resposta contém o token antes de continuar
        if "access_token" not in token_data:
            pytest.fail("A chave 'access_token' não foi encontrada na resposta do endpoint de login.")
            
        return token_data["access_token"]