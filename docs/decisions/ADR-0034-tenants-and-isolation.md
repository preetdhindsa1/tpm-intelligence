# ADR-0034: Tenants and isolation

- **Status:** accepted (plan approved by the owner, 2026-11-26). Built in #230-#232 and #234.
  Cloud changes (the migration on Cloud SQL, the application database role) wait for the
  owner's deploy and Terraform approval.
- **Date:** 2026-11-26

## Context

Wave 6 goal (docs/plan/e2e-plan.md): a company signs up, connects its tools and sees only
its own data, proven by tests. Today there is one implicit tenant:

- 25 tables in `pipeline/store/models.py`, none with a tenant column. The largest is
  `events` (about 391,000 rows locally; the cloud has a similar order).
- Reading is public. Actions need a GitHub login on the `APPROVERS` allowlist, sent by the
  web server in a signed request (ADR-0016: `X-TPM-User`, `X-TPM-Time`, `X-TPM-Signature`).
- Team configs come from `connectors/teams/*.yaml` (ADR-0003). Collectors, the worker and
  the jobs read them directly.

CLAUDE.md section 10 asks for per-tenant isolation "enforced in the API and the database
(row-level security once there is more than one tenant)", tenant data deletable on request,
and every admin action audit-logged. Section 15: "every stored row carries a tenant ID once a
second tenant exists."

## Decision

### 1. One database, a `tenant_id` on every row, Postgres row-level security

- New table `tenants(id text primary key, name, created_at, public bool)`. The id is a short
  slug (`demo`, `acme`), readable in logs and in Secret Manager names.
- The existing public data becomes tenant **`demo`** (`public = true`): Kubernetes, Kafka and
  this repository.
- Every one of the 25 tables gains `tenant_id text not null references tenants(id)`.
  - The migration adds it with the constant default `'demo'`. Postgres 11+ does this without
    rewriting the table, which matters for `events`.
  - Once request scoping lands (#231), a second revision replaces the default with
    `NULLIF(current_setting('app.tenant_id', true), '')`. A write from a session that has
    not set its tenant then **fails** on NOT NULL. `NULLIF` matters: a pooled connection
    that once ran a scoped transaction reads the setting as `''` afterwards, not as missing
    (found in the #231 tests). Until that revision the default stays `'demo'`, so the app
    keeps working between the two PRs.
    There is no silent fallback to `demo`.
- Every unique key gains `tenant_id` as its first column, e.g. `(tenant_id, repo, number)`
  on `pull_requests` and `(tenant_id, key)` on `raid_items`. Two companies can track the same
  public repository, or have the same RAID ID, without colliding.
- **Row-level security** on every tenant table:
  `USING (tenant_id = current_setting('app.tenant_id', true))`, with the same `WITH CHECK`
  (`''` and NULL match no row).
  With no tenant set, `current_setting(..., true)` is NULL and the policy matches no rows,
  so reads fail closed too.
- The API, the worker and the jobs connect as a new role **`tpm_app`**: not the table owner,
  no `BYPASSRLS`. Migrations keep running as the owner. Locally the Compose stack creates
  both roles. In the cloud the role is created by Terraform, which waits for the owner's
  approval.

### 2. Every database session is scoped to one tenant

- `pipeline/store/tenancy.py` registers a session hook that runs
  `SELECT set_config('app.tenant_id', :t, true)` at the start of each transaction (the
  `true` means "this transaction only", so a pooled connection never carries one tenant's
  setting into another request).
- The tenant comes from `session.info["tenant_id"]` when a factory is bound to one tenant
  (`tenant_sessions(factory, tenant)`, used by each tenant's release service), else from a
  context variable, `current_tenant`. The API middleware sets it per request; each job's
  entry point sets it from `TPM_TENANT` (default `demo`). It is per request and per task,
  not process-wide. A plain thread does not inherit it, so code that starts threads
  passes the tenant on (`in_tenant`, `carry`). A thread that forgets runs with no tenant
  and fails closed.
- In-memory caches are per tenant: each private tenant gets its own release service and
  simulator, and the dependencies cache key includes the tenant.
- Background work (pollers, the worker, retro and RAID jobs, the forecast recorder) runs
  **per tenant**, looping over tenants and their connectors (ADR-0035). Queue messages
  carry `tenant_id` as an attribute, next to the trace context.

### 3. How a request picks its tenant

- Header **`X-TPM-Tenant`**. When it is absent the tenant is `demo`, so today's web app and
  every existing link keep working unchanged.
- The header is part of the signature. Signature v2 appends a line with the tenant to the
  HMAC message (`user \n time \n METHOD \n path \n sha256(body) \n tenant`). The API accepts
  v1 (no tenant line) only for `demo`. The web change is small and belongs to cursor-agent.
- **Reading** a `public` tenant (only `demo`) is open, as today. **Reading any other tenant
  needs a signed-in member** of it: 401 if not signed in, 404 if signed in but not a member
  (a non-member learns nothing, not even that the tenant exists).
- **Unknown tenant: 404.** **Tenant table unreachable: 503.** Never a fallback to `demo`.

### 4. Members and roles

- `members(tenant_id, login, role, added_at)`, primary key `(tenant_id, login)`. The login is
  the GitHub login from the signed request. It is stored for access control and is never
  shown in public views (CLAUDE.md section 10).
- Roles:
  - **reader**: sees the tenant's data;
  - **approver**: also takes the actions that need approval today (ADR-0016: exec updates,
    link and RAID decisions, readiness calls, paid AI);
  - **owner**: also manages members, connectors, export and deletion (ADR-0035).
- For `demo` the `APPROVERS` allowlist keeps working: those logins are approvers of `demo`.
  The members table does not replace it there, so the public demo works the same.
- A tenant is created by a signed-in user, who becomes its first owner. Who may create
  tenants is limited by `TENANT_CREATORS` (logins, comma-separated) until sign-up opens to
  everyone. That is an owner decision, so it starts closed.

### 5. Tests that prove isolation (#232)

- CI integration tests run against real Postgres with RLS on, as `tpm_app`:
  - Two tenants, each with releases, PRs, RAID items, decisions and AI usage.
  - **Every** GET route is called as each tenant. No response contains a key, title or
    count that belongs to the other tenant.
  - Raw SQL as `tpm_app` with the other tenant set returns zero rows from each table.
  - A session with no tenant set reads nothing and cannot write.
- A test lists every table in the models and fails if one is missing `tenant_id` or its RLS
  policy, so a new table cannot skip isolation.

## Alternatives considered

- **One database (or one schema) per tenant.** Isolation is strong and needs no policies.
  But Cloud SQL cost grows per tenant (always-on instances, CLAUDE.md section 10 cost
  guardrails), migrations run N times, and cross-tenant operations (the public Portfolio of
  the demo) get harder. Rejected for the demo's scale. It is the upgrade path for a large
  customer that requires it.
- **`tenant_id` filters in application code only, no RLS.** Simpler, but one missed
  `WHERE` leaks data, and CLAUDE.md asks for database enforcement. Rejected. The code
  still scopes queries; RLS is the backstop.
- **Tenant in the URL path (`/t/acme/releases/...`).** Explicit, but it changes every route
  and every web link. Rejected in favour of a header with `demo` as the default.
- **A `tenant_id` default of `'demo'` kept forever.** Easiest migration, but a write that
  forgot its tenant would land in the public demo. Rejected: such writes must fail.

## Trade-offs and consequences

- Every store and job takes a tenant. That is a wide but mechanical change, done table group
  by table group with tests.
- Two GitHub tenants tracking the same public repository store it twice. That is accepted:
  it keeps isolation simple, and each tenant can link it to its own plan.
- RLS adds a predicate on every query. Indexes lead with `tenant_id` so it stays cheap.
- The `events` migration is the risky step in the cloud: an `ALTER TABLE` with a constant
  default does not rewrite rows, but index rebuilds for the new unique keys do take time.
  Measured on a copy of the local database (391,486 events): upgrade about 1 s, downgrade
  about 3 s. It
  runs in a maintenance window the owner approves, with a backup first.
- Revisit if a customer needs physical isolation, or if RLS query plans become a bottleneck
  in the Wave 7 load test.

## AI vs rules

No AI. Isolation is enforced by deterministic code and the database.

## Addendum 1 (2026-11-27): how isolation is enforced and proven (#231, #232)

- **Migrations.**
  - 0013 adds the columns (default `'demo'`).
  - 0014 switches the default to the session's tenant (`NULLIF(current_setting(...), '')`, so
    a write with no tenant fails on NOT NULL).
  - 0015 turns on row-level security with **FORCE** and one policy per table, `members`
    included. The policy is `tenant_id = current_setting('app.tenant_id', true)`, for reads
    and writes. `tenants` has no policy: it is read to resolve a request before any tenant is
    set, and holds only names.
- **No new database role for the cloud.** FORCE binds the table owner. On Cloud SQL the app
  user (`tpm`) owns the tables but is not a superuser, so the policies apply to it as it
  is. **To check after the deploy**: as `tpm`, with no tenant set,
  `SELECT count(*) FROM events` must return 0. If Cloud SQL ever let that user bypass RLS,
  the fallback is the separate `tpm_app` role from the decision above.
- **Locally the Docker user is a superuser**, so it bypasses RLS. The app still scopes
  every session, but the database backstop does not show locally. The proof is in CI:
  `tests/store/test_isolation.py` and `test_isolation_api.py` connect as a role with
  `NOSUPERUSER NOBYPASSRLS`.
- **What the tests prove** (CI, real Postgres):
  - every tenant table has forced RLS and a policy, and a new table without one fails the
    test;
  - each tenant reads only its rows; with no tenant, reads return nothing and writes fail;
  - a tenant cannot write a row for another tenant, move one into it, or update another
    tenant's rows;
  - the same natural key in two tenants does not collide;
  - **every GET route** in the OpenAPI schema (30 or more), called as the demo and as a
    second tenant, returns none of the other tenant's markers and no 5xx. Each tenant's own
    data does come back, so the check is not empty.
- **Found while testing:**
  - FastAPI 0.165 wraps included routers, so `app.routes` hid the RAID, readiness and retro
    routes. The test reads the OpenAPI schema instead.
  - A pooled connection reads the tenant setting as `''` after a scoped transaction ended,
    hence `NULLIF`.
- **Known gaps until #233:**
  - The Portfolio lists the YAML teams for every tenant. Their data is still isolated: a
    private tenant sees "no release yet" for them.
  - The live-update hub announces "release changed" by release key alone, so a second
    tenant tracking the same key may get a needless refresh. It carries no data.
