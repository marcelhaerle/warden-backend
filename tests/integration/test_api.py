from fastapi.testclient import TestClient


def test_root_health_response_shape(client: TestClient):
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"status": "Warden backend is running", "worker": "active"}


def test_search_requires_json_filter(client: TestClient):
    response = client.get("/api/scans/search")

    assert response.status_code == 400
    assert response.json()["detail"] == "Provide json_key/json_value or json_contains"


def test_search_requires_key_and_value_together(client: TestClient):
    response = client.get("/api/scans/search?json_key=warnings")

    assert response.status_code == 400
    assert response.json()["detail"] == "json_key and json_value must be provided together"
