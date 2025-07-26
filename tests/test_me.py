import httpx

def test_get_me(base_url, login_token):
    headers = {
        "Authorization": f"Bearer {login_token}",
        "accept": "application/json"
    }

    response = httpx.get(
        f"{base_url}/me",
        headers=headers,
        params={"local_kw": "teste"}  # <- Correção
    )
    print("Resposta GET /me:", response.text)
    assert response.status_code == 200
