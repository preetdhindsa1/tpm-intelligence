"""Engine and session factories. Database URL comes from ``DATABASE_URL``."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_URL = "postgresql+psycopg://tpm:tpm@localhost:5432/tpm"


def database_url() -> str:
    """``DATABASE_URL`` or the local Compose default."""
    return os.getenv("DATABASE_URL", DEFAULT_URL)


def make_engine(url: str | None = None, *, instrument: bool = True) -> Engine:
    """Create an engine; SQL statements are traced with OpenTelemetry when ``instrument``."""
    engine = create_engine(url or database_url(), pool_pre_ping=True, future=True)
    if instrument:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        SQLAlchemyInstrumentor().instrument(engine=engine)
    return engine


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Commit on success, roll back on error, always close."""
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
