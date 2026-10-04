from fastapi.testclient import TestClient
from starlette.routing import WebSocketRoute


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_only_phase_one_to_three_apis_are_registered(client: TestClient) -> None:
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
    assert not any(isinstance(route, WebSocketRoute) for route in client.app.routes)
