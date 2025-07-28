import requests
import uuid

BASE_URL = "https://barbearia-backend-service-198513369137.southamerica-east1.run.app"

def test_criar_usuario_e_autenticar():
    email = f"teste_{uuid.uuid4()}@email.com"
    senha = "teste123"

    usuario = {
        "nome": "Usuário Teste",
        "email": email,
        "senha": senha
    }

    r1 = requests.post(f"{BASE_URL}/usuarios", json=usuario)
    assert r1.status_code == 200
    user_data = r1.json()
    assert user_data["email"] == email
    assert "id" in user_data

    login_data = {
        "username": email,
        "password": senha
    }

    r2 = requests.post(
        f"{BASE_URL}/login",
        data=login_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    assert r2.status_code == 200
    token_data = r2.json()
    assert "access_token" in token_data

    headers = {
        "Authorization": f"Bearer {token_data['access_token']}",
        "accept": "application/json"
    }

    r3 = requests.get(f"{BASE_URL}/me", headers=headers, params={"local_kw": "teste"})  # <- Correção
    print("Resposta /me:", r3.text)
    assert r3.status_code == 200
