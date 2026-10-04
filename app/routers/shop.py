from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_player
from app.models import InventoryItem, Player
from app.schemas import (
    ErrorResponse,
    PurchaseData,
    PurchaseItem,
    PurchaseRequest,
    PurchaseResponse,
    ShopProduct,
    ShopProductsResponse,
)
from app.shop_config import SHOP_PRODUCTS

router = APIRouter(prefix="/shop", tags=["shop"])


@router.get(
    "/products",
    response_model=ShopProductsResponse,
    responses={401: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
def get_products(
    player: Annotated[Player, Depends(get_current_player)],
) -> ShopProductsResponse:
    return ShopProductsResponse(
        data=[
            ShopProduct(id=product_id, **product)
            for product_id, product in SHOP_PRODUCTS.items()
        ]
    )


@router.post(
    "/purchase",
    response_model=PurchaseResponse,
    responses={
        400: {"model": ErrorResponse, "description": "金币不足（code=1001）"},
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse, "description": "商品不存在（code=1002）"},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def purchase(
    payload: PurchaseRequest,
    player: Annotated[Player, Depends(get_current_player)],
    db: Annotated[Session, Depends(get_db)],
) -> PurchaseResponse | JSONResponse:
    product = SHOP_PRODUCTS.get(payload.product_id)
    if product is None:
        db.rollback()
        return JSONResponse(
            status_code=404,
            content=ErrorResponse(code=1002, message="product not found").model_dump(),
        )

    # 鉴权已读取玩家；加锁重读金币，串行处理同一玩家的购买。
    db.refresh(player, with_for_update=True)
    if player.gold < product["price"]:
        db.rollback()
        return JSONResponse(
            status_code=400,
            content=ErrorResponse(code=1001, message="not enough gold").model_dump(),
        )

    # 锁定读取最新库存，避免 MySQL 默认隔离级别读取鉴权时的旧快照。
    inventory = db.scalar(
        select(InventoryItem)
        .where(
            InventoryItem.player_id == player.id,
            InventoryItem.item_id == product["item_id"],
        )
        .with_for_update()
    )
    if inventory is None:
        inventory = InventoryItem(
            player_id=player.id, item_id=product["item_id"], count=0
        )
        db.add(inventory)

    player.gold -= product["price"]
    inventory.count += 1
    # 金币和库存只提交一次；数据库异常由 get_db 回滚并返回 503。
    db.commit()
    return PurchaseResponse(
        data=PurchaseData(
            gold=player.gold,
            item=PurchaseItem(item_id=inventory.item_id, count=inventory.count),
        )
    )
