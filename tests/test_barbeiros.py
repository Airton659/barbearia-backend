import httpx

def test_listar_barbeiros(base_url):
    response = httpx.get(f"{base_url}/barbeiros")
    print("Resposta /barbeiros:", response.text)
    assert response.status_code == 200
