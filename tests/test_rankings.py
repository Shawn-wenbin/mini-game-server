import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.models import Player


def test_empty_rankings_are_public(client: TestClient) -> None:
    response = client.get("/api/v1/rankings")

    assert response.status_code == 200
    assert response.json() == {"code": 0, "message": "ok", "data": []}


def test_rankings_sort_scores_descending_and_ties_by_id(
    client: TestClient, db_engine: Engine
) -> None:
    with Session(db_engine) as session:
        # 同分时用户名排序与 ID 排序相反，确保次序由 ID 决定。
        for username, score in [
            ("zebra", 80), ("alice", 80), ("winner", 100), ("newbie", 0)
        ]:
            session.add(Player(username=username, high_score=score))
            session.flush()
        session.commit()

    response = client.get("/api/v1/rankings")

    assert response.status_code == 200
    assert response.json() == {
        "code": 0,
        "message": "ok",
        "data": [
            {"rank": 1, "username": "winner", "score": 100},
            {"rank": 2, "username": "zebra", "score": 80},
            {"rank": 3, "username": "alice", "score": 80},
            {"rank": 4, "username": "newbie", "score": 0},
        ],
    }
    limited = client.get("/api/v1/rankings?limit=2").json()["data"]
    assert limited == response.json()["data"][:2]


@pytest.mark.parametrize("query,count", [("", 20), ("?limit=1", 1), ("?limit=100", 100)])
def test_rankings_limit_defaults_and_bounds(
    client: TestClient, db_engine: Engine, query: str, count: int
) -> None:
    with Session(db_engine) as session:
        session.add_all(
            Player(username=f"player_{score}", high_score=score)
            for score in range(101)
        )
        session.commit()

    response = client.get(f"/api/v1/rankings{query}")

    assert response.status_code == 200
    assert response.json()["data"] == [
        {"rank": rank, "username": f"player_{101 - rank}", "score": 101 - rank}
        for rank in range(1, count + 1)
    ]


@pytest.mark.parametrize("limit", ["0", "-1", "101", "text", "1.5", "true", ""])
def test_rankings_reject_invalid_limit(client: TestClient, limit: str) -> None:
    response = client.get("/api/v1/rankings", params={"limit": limit})

    assert response.status_code == 422
    assert response.json()["code"] == 422
    assert response.json()["data"] is None


def test_rankings_database_failure_returns_common_error(
    client: TestClient, monkeypatch
) -> None:
    def fail_read(session: Session, *args: object, **kwargs: object) -> None:
        raise OperationalError("SELECT", None, RuntimeError("simulated read failure"))

    monkeypatch.setattr(Session, "scalars", fail_read)
    response = client.get("/api/v1/rankings")

    assert response.status_code == 503
    assert response.json() == {"code": 503, "message": "database unavailable", "data": None}
