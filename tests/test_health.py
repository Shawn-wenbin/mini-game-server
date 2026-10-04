from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_phase_one_to_four_routes_are_registered(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert set(response.json()["paths"]) == {
        "/api/v1/health",
        "/api/v1/auth/login",
        "/api/v1/player/me",
        "/api/v1/shop/products",
        "/api/v1/shop/purchase",
        "/api/v1/bag",
        "/api/v1/game/result",
        "/api/v1/rankings",
    }
    assert client.app.url_path_for("websocket_training") == "/api/v1/ws"
