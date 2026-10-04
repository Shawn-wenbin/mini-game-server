from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints


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


class ErrorResponse(BaseModel):
    code: int
    message: str
    data: None = None
