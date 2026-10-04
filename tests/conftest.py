from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

import app.main as main
from app.database import get_db


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
def client(db_engine: Engine) -> Iterator[TestClient]:
    test_session = sessionmaker(bind=db_engine, expire_on_commit=False)

    def override_db() -> Iterator[Session]:
        with test_session() as session:
            yield session

    main.app.dependency_overrides[get_db] = override_db
    try:
        # 使用上下文管理器，实际执行 startup 建表与 shutdown 生命周期。
        with TestClient(main.app) as test_client:
            yield test_client
    finally:
        main.app.dependency_overrides.clear()
