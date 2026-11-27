"""Local load-test setup (#258): a second tenant as heavy as the demo, and an app role.

Run against a *copy* of the local database (never the cloud), as its owner::

    DATABASE_URL=postgresql+psycopg://tpm:tpm@postgres:5432/tpm_load \
        python scripts/load/seed_second_tenant.py --password <random>

It creates tenant ``acme`` (owner login ``loadtest``) with a copy of every demo event and
the demo's team configs, so row-level security filters two equally large tenants. Then it
creates ``tpm_load_app``, a NOSUPERUSER NOBYPASSRLS role, which is how the API connects on
Cloud SQL: the local superuser bypasses row-level security and would measure nothing.
"""

from __future__ import annotations

import argparse
import re

from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from connectors.admin import AdminError, PostgresTenantAdmin
from connectors.load import load_teams
from connectors.store import PostgresTeamConfigStore
from pipeline.store.session import make_engine
from pipeline.store.tenancy import DEMO, tenant_sessions, use_tenant

TENANT, OWNER, ROLE = "acme", "loadtest", "tpm_load_app"
COLUMNS = ("event_id, event_type, schema_version, source, subject_kind, subject_key, "
           "occurred_at, observed_at, ingested_at, payload")  # fmt: skip


def main() -> None:
    """Seed once; safe to re-run (it skips what exists)."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--password", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9]{16,64}", args.password):
        raise SystemExit("password: 16-64 letters and digits")
    engine = make_engine()
    if engine.url.database in (None, "tpm"):
        raise SystemExit("refusing: point DATABASE_URL at a copy (e.g. tpm_load), not tpm")
    factory = sessionmaker(engine)
    try:
        PostgresTenantAdmin(factory).create(TENANT, "Acme (load test)", OWNER)
    except AdminError as exc:
        print(f"tenant: {exc}")
    with use_tenant(TENANT), factory() as s, s.begin():
        have = s.scalar(text("SELECT count(*) FROM events WHERE tenant_id = :t"), {"t": TENANT})
        if not have:  # the owner role bypasses RLS, so it can read the demo's rows here
            s.execute(text(f"INSERT INTO events ({COLUMNS}) SELECT {COLUMNS} FROM events "  # noqa: S608
                           "WHERE tenant_id = :demo ORDER BY id"), {"demo": DEMO})  # fmt: skip
    with use_tenant(DEMO):
        teams = list(load_teams(DEMO).values())
    store = PostgresTeamConfigStore(tenant_sessions(factory, TENANT))
    for team in teams:
        store.put(team.model_dump(mode="json"))
    # Role DDL takes no bound parameters: ROLE is a constant and the password was checked.
    exists = f"SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}'"  # noqa: S608
    create = (f"DO $$ BEGIN IF NOT EXISTS ({exists}) THEN "
              f"CREATE ROLE {ROLE} LOGIN NOSUPERUSER NOBYPASSRLS; END IF; END $$;")  # fmt: skip
    with engine.begin() as conn:
        conn.execute(text(create))
        conn.execute(text(f"ALTER ROLE {ROLE} PASSWORD '{args.password}'"))
        conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {ROLE}"))
        conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA "
                          f"public TO {ROLE}"))  # fmt: skip
        conn.execute(text(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {ROLE}"))
        counts = conn.execute(text("SELECT tenant_id, count(*) FROM events GROUP BY 1")).all()
    print(dict(counts), f"teams for {TENANT}: {[t.id for t in teams]}")


if __name__ == "__main__":
    main()
