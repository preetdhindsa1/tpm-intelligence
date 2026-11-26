"""Real-Postgres fixtures: a throwaway database migrated with Alembic per test session."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from pipeline.store.session import database_url

pytestmark = pytest.mark.integration


def alembic_config(url: str) -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    cfg.attributes["configure_logger"] = False
    return cfg


@pytest.fixture(scope="session")
def db_url() -> Iterator[str]:
    """Create ``tpm_test_<random>``, migrate to head, drop it afterwards."""
    base = make_url(database_url())
    admin = create_engine(base, isolation_level="AUTOCOMMIT")
    name = f"tpm_test_{uuid.uuid4().hex[:8]}"
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
    except OperationalError:
        pytest.skip("Postgres not reachable at DATABASE_URL")
    url = base.set(database=name).render_as_string(hide_password=False)
    command.upgrade(alembic_config(url), "head")
    yield url
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    admin.dispose()


@pytest.fixture(scope="session")
def engine(db_url: str) -> Iterator[Engine]:
    eng = create_engine(db_url)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    """Session inside an outer transaction that is rolled back after each test."""
    with engine.connect() as conn:
        outer = conn.begin()
        sess = Session(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield sess
        finally:
            sess.close()
            outer.rollback()


APP_ROLE = "tpm_app_test"


@pytest.fixture(scope="session")
def app_engine(engine: Engine, db_url: str) -> Iterator[Engine]:
    """An engine for a role with no superuser and no BYPASSRLS, like the cloud app user."""
    password = uuid.uuid4().hex
    # Role DDL cannot take bound parameters; APP_ROLE is a constant and the password a UUID.
    exists = f"SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}'"  # noqa: S608
    create = (
        f"DO $$ BEGIN IF NOT EXISTS ({exists}) THEN "
        f"CREATE ROLE {APP_ROLE} LOGIN NOSUPERUSER NOBYPASSRLS; END IF; END $$;"
    )
    with engine.begin() as conn:
        conn.execute(text(create))
        conn.execute(text(f"ALTER ROLE {APP_ROLE} PASSWORD '{password}'"))
        conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}"))
        conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public "
                          f"TO {APP_ROLE}"))  # fmt: skip
        conn.execute(text(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}"))
        conn.execute(text("INSERT INTO tenants (id, name) VALUES ('acme', 'Acme'), "
                          "('globex', 'Globex') ON CONFLICT DO NOTHING"))  # fmt: skip
    url = make_url(db_url).set(username=APP_ROLE, password=password)
    eng = create_engine(url)
    yield eng
    eng.dispose()
