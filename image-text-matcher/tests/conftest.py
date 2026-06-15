from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.base import Base
from app.db.session import get_db
from app.main import app


@pytest.fixture
def db_session(tmp_path: Path) -> Session:
    database_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    testing_session_local = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        future=True,
    )
    Base.metadata.create_all(bind=engine)

    session = testing_session_local()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def _build_client(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


@pytest.fixture
def unauthenticated_client(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    client = _build_client(db_session, monkeypatch)
    try:
        yield client
    finally:
        client.close()
        app.dependency_overrides.clear()


@pytest.fixture
def client(unauthenticated_client: TestClient) -> TestClient:
    response = unauthenticated_client.post(
        "/auth/login",
        json={"username": "testadmin", "password": "testadmin"},
    )
    assert response.status_code == 200
    return unauthenticated_client
