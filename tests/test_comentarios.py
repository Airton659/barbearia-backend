import httpx

def test_listar_comentarios_postagem_inexistente(base_url):
    import uuid
    response = httpx.get(f"{base_url}/comentarios/{uuid.uuid4()}")
    assert response.status_code in [200, 404]
