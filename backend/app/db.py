"""Database engine, session factory and declarative base.

SQLite on purpose: the whole system must run from one folder on one laptop with
no server process (see PLAN.md D8). WAL mode plus a short busy timeout keeps the
background pipeline thread from colliding with request threads.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config.settings import settings


class Base(DeclarativeBase):
    """Declarative base for every NagarNetra table."""


def _build_engine(url: str | None = None) -> Engine:
    database_url = url or settings.resolved_database_url
    connect_args: dict[str, Any] = {}
    if database_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False, "timeout": 30}
    return create_engine(
        database_url,
        connect_args=connect_args,
        future=True,
        pool_pre_ping=True,
    )


engine: Engine = _build_engine()


@event.listens_for(Engine, "connect")
def _set_sqlite_pragmas(dbapi_connection: Any, _connection_record: Any) -> None:
    """Enable foreign keys and WAL for every SQLite connection."""
    module_name = type(dbapi_connection).__module__
    if not module_name.startswith("sqlite3"):
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
    finally:
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def session_scope() -> Session:
    """Standalone session for background tasks and scripts.

    The caller owns commit/rollback/close. Used by the pipeline worker, which
    runs outside the request lifecycle.
    """
    return SessionLocal()


def init_db() -> None:
    """Create every table. Idempotent."""
    from app import models  # noqa: F401  (import registers the mappers)

    Base.metadata.create_all(bind=engine)
