import logging
from collections.abc import Iterator

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    # 每个请求单独创建 Session，退出时关闭并归还连接。
    with SessionLocal() as session:
        try:
            yield session
        except SQLAlchemyError as exc:
            session.rollback()
            logger.exception("数据库操作失败")
            raise HTTPException(
                status_code=503, detail="database unavailable"
            ) from exc
