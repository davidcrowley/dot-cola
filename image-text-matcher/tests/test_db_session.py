from __future__ import annotations

import pytest
from sqlalchemy import MetaData
from sqlalchemy.exc import OperationalError

from app.db import session


def test_initialize_database_reports_postgres_connection_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    metadata = MetaData()
    monkeypatch.setattr(
        session.settings,
        "database_url",
        "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/image_text_matcher",
    )

    def fake_create_all(*, bind) -> None:
        raise OperationalError(
            "CREATE TABLE submissions (...)",
            {},
            ConnectionRefusedError("connection refused"),
        )

    monkeypatch.setattr(metadata, "create_all", fake_create_all)

    with pytest.raises(RuntimeError) as exc_info:
        session.initialize_database(metadata)

    message = str(exc_info.value)
    assert "Expected a database server at 127.0.0.1:5432." in message
    assert "docker compose up --build" in message
