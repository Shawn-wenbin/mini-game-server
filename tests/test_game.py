import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.models import InventoryItem, Player


@pytest.fixture
def game_player(client: TestClient) -> dict:
    return client.post("/api/v1/auth/login", json={"username": "alice"}).json()["data"]


def test_results_only_raise_high_score_and_persist(
    client: TestClient, db_engine: Engine, game_player: dict
) -> None:
    headers = {"Authorization": f"Bearer {game_player['token']}"}
    for score, high_score, new_record in [
        (0, 0, False),
        (27, 27, True),
        (27, 27, False),
        (10, 27, False),
        (0, 27, False),
        (100, 100, True),
        (2_147_483_647, 2_147_483_647, True),
    ]:
        response = client.post(
            "/api/v1/game/result", headers=headers, json={"score": score}
        )

        assert response.status_code == 200
        assert response.json() == {
            "code": 0,
            "message": "ok",
            "data": {
                "score": score, "high_score": high_score, "new_record": new_record
            },
        }
        # 每次用独立 Session 确认已提交，且成绩提交不改变玩家资产或背包。
        with Session(db_engine) as session:
            player = session.get(Player, game_player["player"]["id"])
            assert (player.high_score, player.level, player.gold, player.diamond) == (
                high_score, 1, 1000, 100
            )
            assert session.scalar(select(InventoryItem)) is None

        current_player = client.get("/api/v1/player/me", headers=headers).json()["data"]
        login = client.post("/api/v1/auth/login", json={"username": "alice"}).json()
        assert current_player["high_score"] == high_score
        assert login["data"]["player"]["high_score"] == high_score
        assert client.get("/api/v1/rankings").json()["data"] == [
            {"rank": 1, "username": "alice", "score": high_score}
        ]


def test_result_only_updates_authenticated_player(
    client: TestClient, db_engine: Engine, game_player: dict
) -> None:
    bob = client.post("/api/v1/auth/login", json={"username": "bob"}).json()["data"]
    response = client.post(
        "/api/v1/game/result",
        headers={"Authorization": f"Bearer {bob['token']}"},
        json={"score": 80},
    )

    assert response.status_code == 200
    with Session(db_engine) as session:
        assert session.get(Player, bob["player"]["id"]).high_score == 80
        assert session.get(Player, game_player["player"]["id"]).high_score == 0


@pytest.mark.parametrize(
    "payload",
    [{}] + [
        {"score": value}
        for value in [-1, None, 1.5, 27.0, "27", True, False, 2_147_483_648]
    ],
)
def test_invalid_score_does_not_change_persisted_record(
    client: TestClient, db_engine: Engine, game_player: dict, payload: dict
) -> None:
    headers = {"Authorization": f"Bearer {game_player['token']}"}
    first = client.post("/api/v1/game/result", headers=headers, json={"score": 27})
    assert first.status_code == 200
    response = client.post("/api/v1/game/result", headers=headers, json=payload)

    assert response.status_code == 422
    assert response.json()["code"] == 422
    assert response.json()["data"] is None
    with Session(db_engine) as session:
        assert session.get(Player, game_player["player"]["id"]).high_score == 27


@pytest.mark.parametrize(
    "authorization",
    [None, "Bearer invalid", "Basic dev-1", "Bearer dev-0", "Bearer dev-999999"],
)
def test_result_requires_valid_token(
    client: TestClient,
    db_engine: Engine,
    game_player: dict,
    authorization: str | None,
) -> None:
    headers = {"Authorization": authorization} if authorization else {}
    response = client.post("/api/v1/game/result", headers=headers, json={"score": 27})

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {"code": 2001, "message": "invalid dev token", "data": None}
    with Session(db_engine) as session:
        assert session.get(Player, game_player["player"]["id"]).high_score == 0


def test_result_commit_failure_rolls_back_high_score(
    client: TestClient, db_engine: Engine, game_player: dict, monkeypatch
) -> None:
    headers = {"Authorization": f"Bearer {game_player['token']}"}
    first = client.post("/api/v1/game/result", headers=headers, json={"score": 27})
    assert first.status_code == 200

    def fail_commit(session: Session) -> None:
        # 先执行 UPDATE，再模拟提交失败，确认实际写入会被回滚。
        session.flush()
        raise OperationalError("COMMIT", None, RuntimeError("simulated commit failure"))

    monkeypatch.setattr(Session, "commit", fail_commit)
    response = client.post("/api/v1/game/result", headers=headers, json={"score": 100})

    assert response.status_code == 503
    assert response.json() == {"code": 503, "message": "database unavailable", "data": None}
    with Session(db_engine) as session:
        assert session.get(Player, game_player["player"]["id"]).high_score == 27
    current_player = client.get("/api/v1/player/me", headers=headers).json()["data"]
    assert current_player["high_score"] == 27
