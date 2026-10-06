import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from app import database
from app.deps import parse_dev_token
from app.models import Player
from app.schemas import (
    PlayerData,
    WebSocketError,
    WebSocketNotice,
    WebSocketNoticeData,
    WebSocketPing,
    WebSocketPong,
)

router = APIRouter(tags=["websocket"])
logger = logging.getLogger(__name__)


def load_websocket_player(token: str | None) -> PlayerData | None:
    # DEV ONLY / NOT PRODUCTION AUTH：复用 HTTP 登录的开发 token。
    player_id = parse_dev_token(token or "")
    if player_id is None:
        return None
    # 只在鉴权时打开 Session，不让长连接占用数据库连接。
    with database.SessionLocal() as db:
        player = db.get(Player, player_id)
        return PlayerData.model_validate(player) if player is not None else None


@router.websocket("/ws")
async def websocket_training(websocket: WebSocket, token: str | None = None) -> None:
    # 握手后通过统一错误消息反馈鉴权失败；客户端收到 notice 才算鉴权成功。
    await websocket.accept()
    try:
        try:
            player = await run_in_threadpool(load_websocket_player, token)
        except SQLAlchemyError:
            logger.exception("WebSocket 鉴权数据库查询失败")
            await websocket.send_json(
                WebSocketError(code=503, message="database unavailable").model_dump()
            )
            await websocket.close(code=1011, reason="database unavailable")
            return

        if player is None:
            await websocket.send_json(
                WebSocketError(code=2001, message="invalid dev token").model_dump()
            )
            await websocket.close(code=1008, reason="invalid dev token")
            return

        await websocket.send_json(
            WebSocketNotice(
                data=WebSocketNoticeData(
                    player_id=player.id, text=f"Welcome, {player.username}!"
                )
            ).model_dump()
        )
        while True:
            event = await websocket.receive()
            if event["type"] == "websocket.disconnect":
                logger.info( f"[WS {websocket.client} ] disconnect event" )
                return
            if event.get("text") is None:
                logger.info( f"[WS {websocket.client} ] received binary frame, rejecting" )
                await websocket.send_json(
                    WebSocketError(
                        code=422, message="binary websocket messages are not supported"
                    ).model_dump()
                )
                await websocket.close(code=1003, reason="unsupported data")
                return
            text = event[ "text" ]
            logger.info( f"[WS {websocket.client} ] RECV {(text)} " )
            try:
                WebSocketPing.model_validate_json(text)
            except ValidationError:
                err = WebSocketError(
                    code= 422 ,
                    message= 'invalid websocket message; expected {"type":"ping"}' ,
                )
                logger.info( f"[WS {websocket.client} ] SEND {err.model_dump_json()} " )
                await websocket.send_json(err.model_dump()) 
                continue
            pong = WebSocketPong()
            logger.info( f"[WS {websocket.client} ] SEND {pong.model_dump_json()} " )
            await websocket.send_json(pong.model_dump())
    except WebSocketDisconnect:
        # 正常断开或发送期间掉线均结束本次连接；重连由客户端发起。
        return
