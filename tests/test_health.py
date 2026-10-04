from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_only_phase_one_and_two_apis_are_registered(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert set(response.json()["paths"]) == {
        "/api/v1/health",
        "/api/v1/auth/login",
        "/api/v1/player/me",
        "/api/v1/shop/products",
        "/api/v1/shop/purchase",
        "/api/v1/bag",
    }
