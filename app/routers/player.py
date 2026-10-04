from typing import Annotated

from fastapi import APIRouter, Depends

from app.deps import get_current_player
from app.models import Player
from app.schemas import ErrorResponse, PlayerData, PlayerResponse

router = APIRouter(prefix="/player", tags=["player"])


@router.get(
    "/me",
    response_model=PlayerResponse,
    responses={401: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
def get_me(player: Annotated[Player, Depends(get_current_player)]) -> PlayerResponse:
    return PlayerResponse(data=PlayerData.model_validate(player))
