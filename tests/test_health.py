def test_root_health(client):
    root = client.get("/")
    assert root.status_code == 200
    data = root.json()
    assert data["status"] == "running"

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
