from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import MetaData, create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


settings = get_settings()

connect_args: dict[str, object] = {}
if settings.database_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(settings.database_url, future=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:  # type: ignore[no-untyped-def]
    if settings.database_url.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def initialize_database(metadata: MetaData) -> None:
    try:
        metadata.create_all(bind=engine)
    except OperationalError as exc:
        raise RuntimeError(_build_database_connection_error(exc)) from exc
    except SQLAlchemyError as exc:
        raise RuntimeError(_build_database_initialization_error(exc)) from exc


def _build_database_connection_error(error: OperationalError) -> str:
    message = [
        f"Database connection failed for {_safe_database_url()}.",
    ]

    url = make_url(settings.database_url)
    if url.host and url.port:
        message.append(f"Expected a database server at {url.host}:{url.port}.")

    if url.get_backend_name().startswith("postgresql"):
        message.append("Start the application with `docker compose up --build`.")

    message.append(f"Original error: {error.orig}")
    return " ".join(message)


def _build_database_initialization_error(error: SQLAlchemyError) -> str:
    return (
        f"Database initialization failed for {_safe_database_url()}. "
        f"Original error: {error}"
    )


def _safe_database_url() -> str:
    return make_url(settings.database_url).render_as_string(hide_password=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
