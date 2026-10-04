from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.models import InventoryItem, Player


def test_new_player_has_empty_bag(client: TestClient) -> None:
    player = client.post("/api/v1/auth/login", json={"username": "alice"}).json()["data"]

    response = client.get(
        "/api/v1/bag", headers={"Authorization": f"Bearer {player['token']}"}
    )

    assert response.status_code == 200
    assert response.json() == {"code": 0, "message": "ok", "data": []}


def test_bag_returns_persisted_items_sorted_and_isolates_players(
    client: TestClient, db_engine: Engine
) -> None:
    alice = client.post("/api/v1/auth/login", json={"username": "alice"}).json()["data"]
    bob = client.post("/api/v1/auth/login", json={"username": "bob"}).json()["data"]
    alice_headers = {"Authorization": f"Bearer {alice['token']}"}
    bob_headers = {"Authorization": f"Bearer {bob['token']}"}

    # 刻意按非 item_id 顺序购买，检查背包顺序和不同玩家的同种物品。
    for product_id in [1002, 1001, 1001]:
        assert client.post(
            "/api/v1/shop/purchase", headers=alice_headers, json={"product_id": product_id}
        ).status_code == 200
    assert client.post(
        "/api/v1/shop/purchase", headers=bob_headers, json={"product_id": 1001}
    ).status_code == 200

    response = client.get("/api/v1/bag", headers=alice_headers)
    assert response.status_code == 200
    assert response.json() == {
        "code": 0,
        "message": "ok",
        "data": [
            {"item_id": 2001, "name": "Potion", "count": 2},
            {"item_id": 2002, "name": "Chest", "count": 1},
        ],
    }
    assert client.get("/api/v1/bag", headers=bob_headers).json() == {
        "code": 0,
        "message": "ok",
        "data": [{"item_id": 2001, "name": "Potion", "count": 1}],
    }

    with Session(db_engine) as session:
        assert session.get(Player, alice["player"]["id"]).gold == 500
        assert session.get(Player, bob["player"]["id"]).gold == 900
        assert len(session.scalars(select(InventoryItem)).all()) == 3
