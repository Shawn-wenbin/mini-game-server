from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_player
from app.models import InventoryItem, Player
from app.schemas import BagItem, BagResponse, ErrorResponse
from app.shop_config import ITEM_NAMES

router = APIRouter(tags=["bag"])


@router.get(
    "/bag",
    response_model=BagResponse,
    responses={401: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
def get_bag(
    player: Annotated[Player, Depends(get_current_player)],
    db: Annotated[Session, Depends(get_db)],
) -> BagResponse:
    items = db.scalars(
        select(InventoryItem)
        .where(InventoryItem.player_id == player.id)
        .order_by(InventoryItem.item_id)
    )
    return BagResponse(
        data=[
            BagItem(
                item_id=item.item_id,
                name=ITEM_NAMES.get(item.item_id, "Unknown"),
                count=item.count,
            )
            for item in items
        ]
    )
