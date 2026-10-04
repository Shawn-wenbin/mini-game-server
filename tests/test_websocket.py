import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from starlette.websockets import WebSocketDisconnect

from app.models import InventoryItem, Player


def login(client: TestClient, username: str = "alice") -> dict:
    response = client.post("/api/v1/auth/login", json={"username": username})
    assert response.status_code == 200
    return response.json()["data"]


def notice(player: dict) -> dict:
    return {
        "type": "notice",
        "code": 0,
        "message": "ok",
        "data": {"player_id": player["id"], "text": f"Welcome, {player['username']}!"},
    }


PONG = {"type": "pong", "code": 0, "message": "ok", "data": None}


def test_welcome_is_pushed_before_ping_and_heartbeats_do_not_access_database(
    client: TestClient, db_engine: Engine, monkeypatch
) -> None:
    data = login(client, "小明")
    with client.websocket_connect(f"/api/v1/ws?token={data['token']}") as ws:
        # 客户端无需先发送消息，服务端鉴权成功就主动推送欢迎通知。
        assert ws.receive_json() == notice(data["player"])
        assert db_engine.pool.checkedout() == 0

        def fail_read(*args: object, **kwargs: object) -> None:
            pytest.fail("心跳不应访问数据库")

        monkeypatch.setattr(Session, "get", fail_read)
        for _ in range(3):
            ws.send_json({"type": "ping"})
            assert ws.receive_json() == PONG
        assert db_engine.pool.checkedout() == 0


@pytest.mark.parametrize(
    "query",
    [
        "", "?token=", "?token=invalid", "?token=dev-0", "?token=dev--1",
        "?token=dev-01", "?token=dev-1-extra", "?token=dev-999999",
        "?token=dev-2147483648", "?token=dev-" + "9" * 100,
    ],
)
def test_invalid_token_sends_error_then_closes(client: TestClient, query: str) -> None:
    login(client)
    with client.websocket_connect(f"/api/v1/ws{query}") as ws:
        assert ws.receive_json() == {
            "type": "error", "code": 2001, "message": "invalid dev token", "data": None,
        }
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == 1008
        assert exc.value.reason == "invalid dev token"


@pytest.mark.parametrize(
    "message",
    [
        "ping", "{", "null", "[]", '"ping"', "true", "1", "{}",
        '{"type":"pong"}', '{"type":1}', '{"type":"ping","extra":1}',
    ],
)
def test_invalid_text_sends_error_and_connection_remains_usable(
    client: TestClient, message: str
) -> None:
    data = login(client)
    with client.websocket_connect(f"/api/v1/ws?token={data['token']}") as ws:
        assert ws.receive_json() == notice(data["player"])
        ws.send_text(message)
        assert ws.receive_json() == {
            "type": "error", "code": 422,
            "message": 'invalid websocket message; expected {"type":"ping"}',
            "data": None,
        }
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == PONG


def test_binary_message_sends_error_then_closes(client: TestClient) -> None:
    data = login(client)
    with client.websocket_connect(f"/api/v1/ws?token={data['token']}") as ws:
        ws.receive_json()
        ws.send_bytes(b'{"type":"ping"}')
        assert ws.receive_json() == {
            "type": "error", "code": 422,
            "message": "binary websocket messages are not supported", "data": None,
        }
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == 1003


def test_auth_database_failure_releases_connection_and_closes(
    client: TestClient, db_engine: Engine, monkeypatch
) -> None:
    data = login(client)
    get_player = Session.get

    def fail_read(session: Session, *args: object, **kwargs: object) -> None:
        # 先实际查询以占用连接，再模拟失败，确认错误分支也会归还连接。
        get_player(session, *args, **kwargs)
        raise OperationalError("SELECT", None, RuntimeError("simulated read failure"))

    monkeypatch.setattr(Session, "get", fail_read)
    with client.websocket_connect(f"/api/v1/ws?token={data['token']}") as ws:
        assert ws.receive_json() == {
            "type": "error", "code": 503, "message": "database unavailable", "data": None,
        }
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == 1011
        assert db_engine.pool.checkedout() == 0


def test_two_players_have_independent_notices_and_heartbeats(client: TestClient) -> None:
    alice = login(client)
    bob = login(client, "bob")
    with client.websocket_connect(f"/api/v1/ws?token={alice['token']}") as alice_ws:
        assert alice_ws.receive_json() == notice(alice["player"])
        with client.websocket_connect(f"/api/v1/ws?token={bob['token']}") as bob_ws:
            assert bob_ws.receive_json() == notice(bob["player"])
            bob_ws.send_json({"type": "ping"})
            alice_ws.send_json({"type": "ping"})
            assert alice_ws.receive_json() == bob_ws.receive_json() == PONG
        alice_ws.send_json({"type": "ping"})
        assert alice_ws.receive_json() == PONG


def test_reconnect_repeats_notice_and_http_restores_persisted_state(
    client: TestClient, db_engine: Engine
) -> None:
    data = login(client)
    headers = {"Authorization": f"Bearer {data['token']}"}
    with client.websocket_connect(f"/api/v1/ws?token={data['token']}") as ws:
        assert ws.receive_json() == notice(data["player"])
        ws.close(code=1000)

    # 断开期间 HTTP 仍可独立使用；重连不修改或重置这些持久化状态。
    purchase = client.post(
        "/api/v1/shop/purchase", headers=headers, json={"product_id": 1001}
    )
    result = client.post("/api/v1/game/result", headers=headers, json={"score": 27})
    assert purchase.status_code == result.status_code == 200
    with Session(db_engine) as db:
        before = db.get(Player, data["player"]["id"])
        assert before is not None
        updated_at = before.updated_at

    with client.websocket_connect(f"/api/v1/ws?token={data['token']}") as ws:
        assert ws.receive_json() == notice(data["player"])
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == PONG
        player = client.get("/api/v1/player/me", headers=headers)
        bag = client.get("/api/v1/bag", headers=headers)
        assert player.status_code == bag.status_code == 200
        assert player.json()["data"] == {
            **data["player"], "gold": 900, "high_score": 27,
        }
        assert bag.json()["data"] == [{"item_id": 2001, "name": "Potion", "count": 1}]

    with Session(db_engine) as db:
        player = db.get(Player, data["player"]["id"])
        item = db.scalar(select(InventoryItem).where(InventoryItem.player_id == player.id))
        assert (player.gold, player.high_score, player.updated_at) == (900, 27, updated_at)
        assert (item.item_id, item.count) == (2001, 1)
