"""SQLAlchemy engine/session management (SQLite by default for Phase 1)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.models.analysis import Base


def _engine_kwargs(database_url: str) -> dict:
    kwargs: dict = {"future": True}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return kwargs


class Database:
    """Thin wrapper owning the engine and session factory."""

    def __init__(self, database_url: str | None = None) -> None:
        url = database_url or get_settings().database_url
        self.engine = create_engine(url, **_engine_kwargs(url))
        self._session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)

    def create_tables(self) -> None:
        import app.models  # noqa: F401 - registers every ORM table on Base

        Base.metadata.create_all(self.engine)
        self._backfill_source_types()

    def _backfill_source_types(self) -> None:
        """One-time correctness fix: rows created before Phase 4 defaulted to
        source_type='REAL'; anything from the mock boards is actually MOCK."""
        from sqlalchemy import text

        with self.engine.begin() as conn:
            conn.execute(text(
                "UPDATE jobs SET source_type = 'MOCK' "
                "WHERE first_source LIKE 'mockboard-%'"
            ))

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


_database: Database | None = None


def get_database() -> Database:
    """Process-wide singleton; tests may call init_database to override."""
    global _database
    if _database is None:
        _database = Database()
        _database.create_tables()
    return _database


def init_database(database_url: str | None = None) -> Database:
    """Create/replace the singleton (used by tests and startup)."""
    global _database
    _database = Database(database_url)
    _database.create_tables()
    return _database


def reset_database() -> None:
    """Drop the singleton reference (test teardown)."""
    global _database
    _database = None
