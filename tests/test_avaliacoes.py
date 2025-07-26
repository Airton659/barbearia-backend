import httpx

def test_listar_avaliacoes_barbeiro_inexistente(base_url):
    import uuid
    response = httpx.get(f"{base_url}/avaliacoes/{uuid.uuid4()}")
    assert response.status_code in [200, 404]
