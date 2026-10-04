import re
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Player

bearer_auth = HTTPBearer(
    auto_error=False,
    description="DEV ONLY / NOT PRODUCTION AUTH：输入登录返回的 dev-{player_id}。",
)


def get_current_player(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_auth)
    ],
    db: Annotated[Session, Depends(get_db)],
) -> Player:
    # DEV ONLY / NOT PRODUCTION AUTH：玩家 ID 可被任意伪造，仅用于本地联调。
    token = credentials.credentials if credentials else ""
    match = re.fullmatch(r"dev-([1-9][0-9]{0,9})", token)
    player_id = int(match[1]) if match else 0
    player = db.get(Player, player_id) if 0 < player_id <= 2_147_483_647 else None
    if player is None:
        raise HTTPException(
            status_code=401,
            detail="invalid dev token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return player
