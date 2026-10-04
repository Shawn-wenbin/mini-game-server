import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.models import InventoryItem, Player


@pytest.fixture
def shop_player(client: TestClient) -> dict:
    return client.post("/api/v1/auth/login", json={"username": "alice"}).json()["data"]


def test_shop_returns_static_products(client: TestClient, shop_player: dict) -> None:
    response = client.get(
        "/api/v1/shop/products",
        headers={"Authorization": f"Bearer {shop_player['token']}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "code": 0,
        "message": "ok",
        "data": [
            {"id": 1001, "name": "Potion", "price": 100, "item_id": 2001},
            {"id": 1002, "name": "Chest", "price": 300, "item_id": 2002},
            {"id": 1003, "name": "Skin A", "price": 500, "item_id": 2003},
        ],
    }


def test_repeated_purchase_deducts_gold_and_accumulates_one_inventory_row(
    client: TestClient, db_engine: Engine, shop_player: dict
) -> None:
    headers = {"Authorization": f"Bearer {shop_player['token']}"}
    for count, gold in [(1, 900), (2, 800)]:
        response = client.post(
            "/api/v1/shop/purchase", headers=headers, json={"product_id": 1001}
        )
        assert response.status_code == 200
        assert response.json() == {
            "code": 0,
            "message": "ok",
            "data": {"gold": gold, "item": {"item_id": 2001, "count": count}},
        }

    # 独立 Session 验证金币与库存均已提交，且重复购买没有重复行。
    with Session(db_engine) as session:
        player = session.get(Player, shop_player["player"]["id"])
        assert player is not None
        assert (player.gold, player.level, player.diamond, player.high_score) == (
            800, 1, 100, 0
        )
        items = session.scalars(select(InventoryItem)).all()
        assert len(items) == 1
        assert (items[0].player_id, items[0].item_id, items[0].count) == (
            player.id, 2001, 2
        )
        assert items[0].created_at is not None
        assert items[0].updated_at is not None

    assert client.get("/api/v1/player/me", headers=headers).json()["data"]["gold"] == 800
    login = client.post("/api/v1/auth/login", json={"username": "alice"})
    assert login.json()["data"]["player"]["gold"] == 800


def test_insufficient_gold_preserves_existing_inventory(
    client: TestClient, db_engine: Engine, shop_player: dict
) -> None:
    headers = {"Authorization": f"Bearer {shop_player['token']}"}
    # 金币恰好等于价格时允许购买，第三次购买必须失败。
    for _ in range(2):
        assert client.post(
            "/api/v1/shop/purchase", headers=headers, json={"product_id": 1003}
        ).status_code == 200

    response = client.post(
        "/api/v1/shop/purchase", headers=headers, json={"product_id": 1003}
    )
    assert response.status_code == 400
    assert response.json() == {"code": 1001, "message": "not enough gold", "data": None}

    with Session(db_engine) as session:
        assert session.get(Player, shop_player["player"]["id"]).gold == 0
        items = session.scalars(select(InventoryItem)).all()
        assert len(items) == 1
        assert (items[0].item_id, items[0].count) == (2003, 2)


def test_insufficient_gold_does_not_create_inventory(
    client: TestClient, db_engine: Engine, shop_player: dict
) -> None:
    with Session(db_engine) as session:
        player = session.get(Player, shop_player["player"]["id"])
        player.gold = 99
        session.commit()

    response = client.post(
        "/api/v1/shop/purchase",
        headers={"Authorization": f"Bearer {shop_player['token']}"},
        json={"product_id": 1001},
    )

    assert response.status_code == 400
    assert response.json()["code"] == 1001
    with Session(db_engine) as session:
        assert session.get(Player, shop_player["player"]["id"]).gold == 99
        assert session.scalar(select(InventoryItem)) is None


def test_unknown_product_does_not_change_state(
    client: TestClient, db_engine: Engine, shop_player: dict
) -> None:
    response = client.post(
        "/api/v1/shop/purchase",
        headers={"Authorization": f"Bearer {shop_player['token']}"},
        json={"product_id": 9999},
    )

    assert response.status_code == 404
    assert response.json() == {"code": 1002, "message": "product not found", "data": None}
    with Session(db_engine) as session:
        assert session.get(Player, shop_player["player"]["id"]).gold == 1000
        assert session.scalar(select(InventoryItem)) is None


@pytest.mark.parametrize(
    "payload",
    [{}] + [{"product_id": value} for value in [0, -1, None, 1001.5, "1001", True]],
)
def test_purchase_rejects_invalid_product_id(
    client: TestClient, db_engine: Engine, shop_player: dict, payload: dict
) -> None:
    response = client.post(
        "/api/v1/shop/purchase",
        headers={"Authorization": f"Bearer {shop_player['token']}"},
        json=payload,
    )

    assert response.status_code == 422
    assert response.json()["code"] == 422
    assert response.json()["data"] is None
    with Session(db_engine) as session:
        assert session.get(Player, shop_player["player"]["id"]).gold == 1000
        assert session.scalar(select(InventoryItem)) is None


@pytest.mark.parametrize("authorization", [None, "Bearer invalid"])
@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("GET", "/api/v1/shop/products", None),
        ("POST", "/api/v1/shop/purchase", {"product_id": 1001}),
        ("GET", "/api/v1/bag", None),
    ],
)
def test_phase_two_apis_require_valid_token(
    client: TestClient,
    db_engine: Engine,
    shop_player: dict,
    authorization: str | None,
    method: str,
    path: str,
    payload: dict | None,
) -> None:
    headers = {"Authorization": authorization} if authorization else {}
    response = client.request(method, path, headers=headers, json=payload)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {"code": 2001, "message": "invalid dev token", "data": None}
    with Session(db_engine) as session:
        assert session.get(Player, shop_player["player"]["id"]).gold == 1000
        assert session.scalar(select(InventoryItem)) is None


def test_database_failure_rolls_back_gold_and_inventory(
    client: TestClient, db_engine: Engine, shop_player: dict, monkeypatch
) -> None:
    def fail_commit(session: Session) -> None:
        # 先写入事务，再模拟提交失败，确认不是仅依赖尚未执行 SQL。
        session.flush()
        raise OperationalError("COMMIT", None, RuntimeError("simulated commit failure"))

    monkeypatch.setattr(Session, "commit", fail_commit)
    response = client.post(
        "/api/v1/shop/purchase",
        headers={"Authorization": f"Bearer {shop_player['token']}"},
        json={"product_id": 1001},
    )

    assert response.status_code == 503
    assert response.json() == {"code": 503, "message": "database unavailable", "data": None}
    with Session(db_engine) as session:
        assert session.get(Player, shop_player["player"]["id"]).gold == 1000
        assert session.scalar(select(InventoryItem)) is None
