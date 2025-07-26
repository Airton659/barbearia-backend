import httpx
import uuid

def test_curtir_postagem_inexistente(base_url, login_token):
    postagem_id = uuid.uuid4()
    response = httpx.post(
        f"{base_url}/postagens/{postagem_id}/curtir",
        headers={
            "Authorization": f"Bearer {login_token}",
            "accept": "application/json"
        },
        params={"local_kw": "teste"}  # <- Correção
    )
    print("Resposta curtir postagem inexistente:", response.text)
    assert response.status_code in [404, 500]
