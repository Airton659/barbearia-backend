import httpx

def test_criar_usuario(base_url):
    payload = {
        "nome": "Novo Usuário",
        "email": "novo@example.com",
        "senha": "novaSenha123"
    }
    response = httpx.post(f"{base_url}/usuarios", json=payload)
    assert response.status_code in (200, 400)  # 400 se já existir

def test_login_usuario(base_url, user_payload):
    response = httpx.post(
        f"{base_url}/login",
        data={
            "username": user_payload["email"],
            "password": user_payload["senha"]
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    assert response.status_code == 200
    assert "access_token" in response.json()
