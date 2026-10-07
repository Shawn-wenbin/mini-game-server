from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_player
from app.models import Player
from app.schemas import (
    ErrorResponse,
    LobbyRewardClaimData,
    LobbyRewardClaimResponse,
    PlayerData,
    PlayerResponse,
)

router = APIRouter(prefix="/player", tags=["player"])

LOBBY_REWARD_GOLD = 100


@router.get(
    "/me",
    response_model=PlayerResponse,
    responses={401: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
def get_me(player: Annotated[Player, Depends(get_current_player)]) -> PlayerResponse:
    return PlayerResponse(data=PlayerData.model_validate(player))


@router.post(
    "/lobby-reward/claim",
    response_model=LobbyRewardClaimResponse,
    responses={
        401: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def claim_lobby_reward(
    player: Annotated[Player, Depends(get_current_player)],
    db: Annotated[Session, Depends(get_db)],
) -> LobbyRewardClaimResponse:
    db.refresh(player, with_for_update=True)
    player.gold += LOBBY_REWARD_GOLD
    db.commit()
    return LobbyRewardClaimResponse(
        data=LobbyRewardClaimData(
            gold=player.gold,
            reward_gold=LOBBY_REWARD_GOLD,
        )
    )
