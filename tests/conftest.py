import os
import uuid

os.environ.setdefault("ENVIRONMENT", "dev")
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.db import get_db
from src.dependencies import get_current_user
from src.main import app
from src.models.base import Base
from src.models.user import User


def _sqlite_date_trunc(unit: str, value: str | None) -> str | None:
    """Emulates Postgres' date_trunc("month", ...) for the SQLite test DB."""
    if value is None:
        return None
    if unit != "month":
        raise NotImplementedError(f"date_trunc unit not supported in tests: {unit}")
    year, month = value.split("-")[:2]
    return f"{year}-{month}-01 00:00:00"


@pytest.fixture()
def engine():
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(test_engine, "connect")
    def _register_sqlite_extras(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")
        dbapi_connection.create_function("date_trunc", 2, _sqlite_date_trunc)

    Base.metadata.create_all(test_engine)
    yield test_engine
    Base.metadata.drop_all(test_engine)
    test_engine.dispose()


@pytest.fixture()
def db_session(engine):
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def make_user(db_session):
    def _make_user() -> User:
        user = User(id=uuid.uuid4(), cognito_sub=f"test-cognito-sub-{uuid.uuid4()}")
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        return user

    return _make_user


@pytest.fixture()
def test_user(make_user) -> User:
    return make_user()


@pytest.fixture()
def other_user(make_user) -> User:
    return make_user()


@pytest.fixture()
def client(db_session, test_user):
    def _override_get_db():
        yield db_session

    def _override_get_current_user():
        return test_user

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_get_current_user
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
