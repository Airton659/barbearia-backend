import httpx

def test_listar_agendamentos_usuario(base_url, login_token):
    response = httpx.get(
        f"{base_url}/agendamentos",
        params={"local_kw": "teste"},  # <- Correção aqui
        headers={
            "Authorization": f"Bearer {login_token}",
            "accept": "application/json"
        }
    )
    print("Resposta /agendamentos:", response.text)
    assert response.status_code in [200, 404]
