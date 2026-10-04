from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Player
from app.schemas import ErrorResponse, LoginData, LoginRequest, LoginResponse, PlayerData

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/login",
    response_model=LoginResponse,
    responses={422: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
def login(payload: LoginRequest, db: Annotated[Session, Depends(get_db)]) -> LoginResponse:
    player = db.scalar(select(Player).where(Player.username == payload.username))
    if player is None:
        player = Player(username=payload.username)
        db.add(player)
        try:
            db.commit()
        except IntegrityError:
            # 同名用户同时首次登录时，回滚并读取另一请求已创建的玩家。
            db.rollback()
            player = db.scalar(select(Player).where(Player.username == payload.username))
            if player is None:
                raise
    return LoginResponse(
        data=LoginData(
            token=f"dev-{player.id}", player=PlayerData.model_validate(player)
        )
    )
