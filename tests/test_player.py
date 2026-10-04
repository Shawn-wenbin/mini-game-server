import pytest
from fastapi.testclient import TestClient


def test_player_me_with_valid_token(client: TestClient) -> None:
    alice = client.post("/api/v1/auth/login", json={"username": "alice"}).json()["data"]
    bob = client.post("/api/v1/auth/login", json={"username": "bob"}).json()["data"]

    response = client.get(
        "/api/v1/player/me", headers={"Authorization": f"Bearer {bob['token']}"}
    )

    assert response.status_code == 200
    assert response.json() == {"code": 0, "message": "ok", "data": bob["player"]}
    assert response.json()["data"]["id"] != alice["player"]["id"]


@pytest.mark.parametrize(
    "authorization",
    [
        None,
        "Bearer",
        "Basic dev-1",
        "Bearer invalid",
        "Bearer dev-0",
        "Bearer dev--1",
        "Bearer dev-01",
        "Bearer dev-1-extra",
        "Bearer dev-999999",
        "Bearer dev-2147483648",
        "Bearer dev-" + "9" * 100,
    ],
)
def test_player_me_rejects_invalid_token(
    client: TestClient, authorization: str | None
) -> None:
    client.post("/api/v1/auth/login", json={"username": "alice"})
    headers = {"Authorization": authorization} if authorization is not None else {}

    response = client.get("/api/v1/player/me", headers=headers)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {
        "code": 2001,
        "message": "invalid dev token",
        "data": None,
    }
