from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

import app.database as database
import app.main as main


@pytest.fixture
def db_engine(tmp_path, monkeypatch) -> Iterator[Engine]:
    # 测试使用独立 SQLite 文件，不读取或修改开发 MySQL 数据。
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, record) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    monkeypatch.setattr(main, "engine", engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def client(db_engine: Engine, monkeypatch) -> Iterator[TestClient]:
    # 保留实际 get_db 的异常处理，以验证购买失败时的回滚和 503 响应。
    monkeypatch.setattr(
        database, "SessionLocal", sessionmaker(bind=db_engine, expire_on_commit=False)
    )
    # 使用上下文管理器，实际执行 startup 建表与 shutdown 生命周期。
    with TestClient(main.app) as test_client:
        yield test_client
