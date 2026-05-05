def test_app_boots(client):
    # Smoke: app boots and returns 404 for unknown route (proving FastAPI is wired)
    response = client.get("/this-does-not-exist")
    assert response.status_code == 404
