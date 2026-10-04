import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.models import Player


def test_login_creates_and_persists_player(
    client: TestClient, db_engine: Engine
) -> None:
    response = client.post("/api/v1/auth/login", json={"username": "alice"})

    assert response.status_code == 200
    data = response.json()["data"]
    assert response.json() == {
        "code": 0,
        "message": "ok",
        "data": {
            "token": f"dev-{data['player']['id']}",
            "player": {
                "id": data["player"]["id"],
                "username": "alice",
                "level": 1,
                "gold": 1000,
                "diamond": 100,
                "high_score": 0,
            },
        },
    }
    # 通过独立 Session 确认提交后的持久化数据，而非只检查响应。
    with Session(db_engine) as session:
        player = session.get(Player, data["player"]["id"])
        assert player is not None
        assert (player.username, player.level, player.gold, player.diamond, player.high_score) == (
            "alice", 1, 1000, 100, 0
        )
        assert player.created_at is not None
        assert player.updated_at is not None


def test_second_login_returns_same_player(
    client: TestClient, db_engine: Engine
) -> None:
    first = client.post("/api/v1/auth/login", json={"username": "alice"})
    second = client.post("/api/v1/auth/login", json={"username": "alice"})

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(Player)) == 1


def test_login_preserves_existing_player_state(
    client: TestClient, db_engine: Engine
) -> None:
    first = client.post("/api/v1/auth/login", json={"username": "alice"}).json()
    with Session(db_engine) as session:
        player = session.get(Player, first["data"]["player"]["id"])
        assert player is not None
        player.gold = 750
        player.high_score = 27
        session.commit()

    response = client.post("/api/v1/auth/login", json={"username": "alice"})

    assert response.status_code == 200
    assert response.json()["data"]["player"]["gold"] == 750
    assert response.json()["data"]["player"]["high_score"] == 27


@pytest.mark.parametrize("username", ["", "   ", "a" * 51, None, 123])
def test_login_rejects_invalid_username(client: TestClient, username) -> None:
    response = client.post("/api/v1/auth/login", json={"username": username})

    assert response.status_code == 422
    assert response.json()["code"] == 422
    assert response.json()["data"] is None


def test_login_strips_username_whitespace(client: TestClient) -> None:
    first = client.post("/api/v1/auth/login", json={"username": " alice "})
    second = client.post("/api/v1/auth/login", json={"username": "alice"})

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
