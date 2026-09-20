"""Shared test fixtures.

Every test runs against a throwaway SQLite file, never the demo database, and
with geocoding switched off so the suite never touches the network.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config.settings import settings  # noqa: E402
from app.db import Base  # noqa: E402
from app.services.bootstrap import ensure_reference_data  # noqa: E402


@pytest.fixture(autouse=True)
def _offline_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test may make a network call, deliberately or by accident."""
    monkeypatch.setattr(settings, "geocoding_enabled", False)
    monkeypatch.setattr(settings, "llm_provider", "none")


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    """A fresh database, seeded with wards and POIs but no complaints."""
    engine = create_engine(f"sqlite:///{(tmp_path / 'test.db').as_posix()}", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    ensure_reference_data(session)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
