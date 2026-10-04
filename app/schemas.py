from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class LoginRequest(BaseModel):
    username: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)
    ]


class PlayerData(BaseModel):
    id: int
    username: str
    level: int
    gold: int
    diamond: int
    high_score: int

    model_config = ConfigDict(from_attributes=True)


class LoginData(BaseModel):
    token: str
    player: PlayerData


class LoginResponse(BaseModel):
    code: Literal[0] = 0
    message: Literal["ok"] = "ok"
    data: LoginData


class PlayerResponse(BaseModel):
    code: Literal[0] = 0
    message: Literal["ok"] = "ok"
    data: PlayerData


class ShopProduct(BaseModel):
    id: int
    name: str
    price: int
    item_id: int


class ShopProductsResponse(BaseModel):
    code: Literal[0] = 0
    message: Literal["ok"] = "ok"
    data: list[ShopProduct]


class PurchaseRequest(BaseModel):
    product_id: Annotated[int, Field(strict=True, gt=0)]


class PurchaseItem(BaseModel):
    item_id: int
    count: int


class PurchaseData(BaseModel):
    gold: int
    item: PurchaseItem


class PurchaseResponse(BaseModel):
    code: Literal[0] = 0
    message: Literal["ok"] = "ok"
    data: PurchaseData


class BagItem(BaseModel):
    item_id: int
    name: str
    count: int


class BagResponse(BaseModel):
    code: Literal[0] = 0
    message: Literal["ok"] = "ok"
    data: list[BagItem]


class GameResultRequest(BaseModel):
    # 与 MySQL 的有符号 INT 范围一致，避免合法请求在写入时溢出。
    score: Annotated[int, Field(strict=True, ge=0, le=2_147_483_647)]


class GameResultData(BaseModel):
    score: int
    high_score: int
    new_record: bool


class GameResultResponse(BaseModel):
    code: Literal[0] = 0
    message: Literal["ok"] = "ok"
    data: GameResultData


class RankingItem(BaseModel):
    rank: int
    username: str
    score: int


class RankingsResponse(BaseModel):
    code: Literal[0] = 0
    message: Literal["ok"] = "ok"
    data: list[RankingItem]


class ErrorResponse(BaseModel):
    code: int
    message: str
    data: None = None
