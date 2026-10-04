from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_player
from app.models import Player
from app.schemas import (
    ErrorResponse,
    GameResultData,
    GameResultRequest,
    GameResultResponse,
    RankingItem,
    RankingsResponse,
)

router = APIRouter(tags=["game"])


@router.post(
    "/game/result",
    response_model=GameResultResponse,
    responses={
        401: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def submit_result(
    payload: GameResultRequest,
    player: Annotated[Player, Depends(get_current_player)],
    db: Annotated[Session, Depends(get_db)],
) -> GameResultResponse:
    # 鉴权已读取玩家；加锁重读最高分，避免并发提交用旧分数覆盖新纪录。
    db.refresh(player, with_for_update=True)
    new_record = payload.score > player.high_score
    if new_record:
        player.high_score = payload.score
    # 数据库异常由 get_db 回滚并返回 503。
    db.commit()
    return GameResultResponse(
        data=GameResultData(
            score=payload.score, high_score=player.high_score, new_record=new_record
        )
    )


@router.get(
    "/rankings",
    response_model=RankingsResponse,
    responses={422: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
def get_rankings(
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> RankingsResponse:
    players = db.scalars(
        select(Player)
        .order_by(Player.high_score.desc(), Player.id.asc())
        .limit(limit)
    )
    return RankingsResponse(
        data=[
            RankingItem(rank=rank, username=player.username, score=player.high_score)
            for rank, player in enumerate(players, start=1)
        ]
    )
