# ADR-0035: Connector framework (team configs per tenant, secrets, audit, deletion, limits)

- **Status:** accepted (plan approved by the owner, 2026-11-26). Built in #233-#235. The
  GitHub App needs the owner's GitHub account, so it is not part of this wave's code.
- **Date:** 2026-11-26

## Context

Today a team is added by writing `connectors/teams/<id>.yaml` (ADR-0003), validated by
`connectors.schema.TeamConfig`, and read through `connectors.load.load_teams()`. That works
for one operator editing the repository. It does not work for companies that sign up
(ADR-0034): they cannot commit YAML, their configs must be isolated per tenant, and their
tokens cannot sit in git or in plain database columns (CLAUDE.md section 10).

CLAUDE.md section 15: "Connectors declare what they provide ... configured per team in
`connectors/teams/<id>.yaml` today, and per tenant in the database once multi-tenancy
exists. Adding a connector must not require changes to `engine/`, `pipeline/`, `verify/` or
`api/`." And: "Tenant data is deletable on request, and every admin action is
audit-logged."

## Decision

### 1. Team configs are per-tenant records, same schema

- New table `team_configs(tenant_id, team_id, config jsonb, version, updated_at)`, primary
  key `(tenant_id, team_id)`, under RLS like every tenant table (ADR-0034).
- `config` is exactly what a YAML file holds, validated by the **same** `TeamConfig` model
  on every write and read. There is one schema and no second format.
- `connectors.load.load_teams(tenant)` returns the tenant's configs:
  - `demo`: from the YAML files, as today. The repository stays the source of truth for the
    public demo, and the YAML tests still apply.
  - any other tenant: from `team_configs`.
  The old zero-argument call keeps meaning `demo` while callers move over, then goes away.
- Each change stores a new `version`, and the previous body goes to the audit log, so a
  config change can be traced and undone.

### 2. Secrets by reference, never stored

- A config names secrets; it never holds them. For example
  `planning: {source: github, token_ref: github-token}`.
- Resolution (`connectors/secrets.py`):
  - in the cloud, Secret Manager secret **`tenant-<tenant_id>-<ref>`**, read by the service
    account;
  - locally, the environment variable **`TENANT_<TENANT_ID>_<REF>`** (upper case, `-` →
  `_`).
- `demo` keeps today's variables (`GITHUB_TOKEN`, ...) so nothing changes for it.
- Read-only scopes stay the rule (CLAUDE.md section 7). The Connect page asks for a
  fine-grained, read-only token.
- Missing secret: that connector is skipped with a reason shown on the Connect page, and
  the other connectors still run. A wrong secret never falls back to another tenant's or
  to `demo`'s.
- **GitHub App.** Installing a GitHub App per organization is the better long-term path
  (scoped, revocable, no personal token). Creating the App needs the owner's GitHub
  account, so this wave supports tokens by reference and leaves an `auth: github_app`
  option in the schema for when the App exists.

### 3. Audit log

- `audit_log(id, tenant_id, at, actor_login, action, target, details jsonb)` is
  append-only: a trigger refuses UPDATE and DELETE, as for `readiness_decisions`. It is under
  RLS, so a tenant sees only its own entries.
- Logged actions:
  - member added, removed or role changed;
  - connector created, changed or deleted (with the old config, never a secret);
  - export started;
  - deletion requested and done;
  - usage limit changed.
- The login is stored for audit. Views show the role, as elsewhere (CLAUDE.md section 10).

### 4. Export and deletion

- **Export** (owner only): one JSON Lines file per table, holding that tenant's rows, read
  with RLS on so it cannot include another tenant's data. It is produced on request, not
  kept.
- **Deletion** (owner only, typed confirmation in the web): deletes the tenant's rows from
  every table in one transaction, then the tenant row, and asks Secret Manager to delete
  `tenant-<id>-*`. The audit log keeps one final "tenant deleted" entry. That row has the
  tenant id and time but no data, and lives outside the deleted tenant (under `system`), so
  the deletion itself is provable.
- The append-only triggers (`readiness_decisions`, `retro_runs`, `audit_log`) allow DELETE
  only through the deletion function, which sets `app.deleting_tenant` for its transaction.
  Ordinary sessions still cannot edit history.
- `demo` cannot be deleted through the API.

### 5. Usage limits

- `tenants` gains `ai_daily_budget_usd` (default $0.50; `demo` keeps the $2/day of CLAUDE.md
  section 8) and `max_teams` (default 3).
- The AI gateway's budget check is per tenant: slow down at 80%, pause non-essential AI at
  100%, as today. Spend is recorded per tenant in `ai_usage`.
- Collectors respect `max_teams`, and a poll interval no shorter than the demo's.

### 6. One new connector: GitLab (#235)

GitLab over Linear because gitlab.com has public projects readable through its API without
an account. That gives a public proof dataset (CLAUDE.md principle 7), and the collector
can be tested on real data. Linear has no public workspaces, so it would need a sample
workspace that someone owns. Before any code, real API calls check what is available
(merge requests, approvals, pipelines, milestones), the rate limits and the terms. The
evidence goes in an addendum here. The collector emits the existing normalized events, so
`engine/`, `pipeline/`, `verify/` and `api/` do not change for it.

## Alternatives considered

- **Keep YAML for everyone, one directory per tenant.** No database change, but companies
  cannot edit files, there is no isolation in the database, and no audit trail. Rejected.
- **A separate, looser schema for database configs.** It would drift from the YAML schema
  that the tests protect. Rejected: one `TeamConfig`.
- **Encrypt tokens in a database column.** That keeps key management inside the app, and a
  database leak plus the key leaks every token. Rejected: Secret Manager, by reference.
- **Soft delete (a `deleted_at` flag).** Easy to undo, but it is not deletion on request.
  Rejected. Export first if the customer wants a copy.

## Trade-offs and consequences

- Collectors and jobs loop over tenants. A slow tenant must not starve others: each has its
  own poll schedule and backoff.
- Two code paths load configs (YAML for `demo`, database for others). They share the schema
  and tests, and the YAML path stays because the public demo is configured in the open.
- Secret Manager names are predictable (`tenant-<id>-<ref>`). Access is by IAM, not by
  obscurity.
- Revisit when the GitHub App exists (switch GitHub to it by default) and when a tenant
  needs more than tokens (OAuth for Jira Cloud).

## AI vs rules

No AI. Configs, secrets, audit and deletion are deterministic. AI budgets are enforced by
the existing gateway, now per tenant.


## Addendum 1 (2026-11-27): built (#233)

- **`team_configs`** (migration 0016): primary key `(tenant_id, team_id)`, forced RLS like
  every tenant table, each body validated by `TeamConfig` on write and on read.
  `connectors/store.py` holds the Postgres store and an in-memory store for tests.
- **`load_teams()` is per tenant.** With no argument it uses the current tenant: YAML for
  the demo, `team_configs` for the others (cached for 30 s per tenant, cleared after a
  change). **With no tenant it raises** rather than hand out the demo's teams. That caught
  one real case: the API read meeting-doc titles from the team configs once at start-up,
  outside any tenant. They are now read per request.
- **Secrets:** `TeamConfig.secret_refs` maps a purpose to a reference (`{"github":
  "github-token"}`). The schema refuses anything that is not a short name, so a pasted
  token cannot reach the database. `connectors/secrets.py` resolves a reference to
  Secret Manager `tenant-<id>-<ref>` when `SECRETS_BACKEND=gcp`, else to the environment
  variable `TENANT_<ID>_<REF>`. `team_secret(team, purpose, demo_env)` gives the demo its
  old variable and a private tenant only its own reference, with no fallback. The GitHub
  poller uses it.
- **API:** `GET /tenants/{id}/connectors` (members; the demo's are the YAML files),
  `PUT` and `DELETE /tenants/{id}/connectors/{team_id}` (owners; never the demo). The path's
  tenant must equal the request's tenant, or 404. The response lists each reference's
  Secret Manager name and whether it resolves, never its value.
- **Not yet, and needed before a second organization collects its own data:**
  - the worker stores events for one tenant (`TPM_TENANT`), so a private tenant's poll needs
    the tenant in each queue message and a worker that honours it;
  - a release calendar inside the config (today it is a file in the repository);
  - one scheduled poll per tenant.

  These are the next step of #233.


## Addendum 2 (2026-11-27): tenants, members, audit, export, deletion, limits (#234)

- **Migration 0017:**
  - `audit_log` (append-only, under RLS);
  - `tenants.ai_daily_budget_usd` (default $0.50; the demo $2.00) and `max_teams` (default 3;
    the demo 50);
  - a `system` tenant that holds the final "tenant deleted" entries.
- **Deletion and the append-only rules.** The five append-only triggers (events, forecast
  snapshots, readiness decisions, retro runs, audit log) now allow `DELETE` in one case:
  the deletion function's own transaction, which sets `app.deleting_tenant` to the same
  tenant its session is scoped to. `UPDATE` and `TRUNCATE` are still refused, and so is any
  other `DELETE` (tested). Deletion removes the tenant's rows table by table, children first,
  with an explicit `WHERE tenant_id = ...` as well as RLS (a superuser would bypass RLS),
  then the tenant row. It leaves one `system` audit entry with the row count and no data.
- **Export** streams one JSON line per row the tenant owns, read with the tenant set and an
  explicit filter. The export itself is audited.
- **Members:**
  - roles are `reader`, `approver` and `owner`;
  - an organization always keeps at least one owner (409);
  - audit entries show the role, never the login.
- **Creating organizations** is limited to `TENANT_CREATORS` (logins). It starts empty, so
  creation stays closed until the owner opens it.
- **AI budget per tenant.** The gateway takes a `cap()` for the current tenant: the demo's
  $2/day from the settings, else the tenant's limit. Spend comes from `ai_usage` under RLS,
  so cap and spend always belong to the same tenant. The API's fact-sheet cache key now
  includes the tenant.
- **Connector changes are audited**, with the new config (references only, never secret
  values). Adding a team beyond `max_teams` is refused (409).

## Addendum 3 (2026-11-27): collection per tenant (#233 part 2)

- **The tenant travels with each event.** `EventPublisher` stamps `tenant_id` on every
  queue message and refuses to publish with no tenant. The consumer stores each message
  for its own tenant: batches are split per tenant, a failed group falls back to one
  message at a time without blocking the others, and the worker's own tenant does not
  decide anything. A message from before this change has no tenant and is the demo's,
  which it was.
- **Release dates in the config.** `calendar` takes either `path` (a file in this
  repository, as the demo teams do) or inline `releases` (a tenant that signs up). Exactly
  one is allowed, and the dates must be in order. `connectors.load.team_calendar()` reads
  either; the poller and `release_plan` use it.
- **One scheduled poll for every organization.** `python -m collectors.github_poller
  --all-tenants` polls each private tenant's teams under that tenant, with its own token,
  for the release its calendar says is running (cycle started, shipped at most 7 days
  ago). A team with no current release or no token is skipped and logged. One tenant's
  failure does not stop the others. Scheduling it in the cloud is one Cloud Scheduler
  job, a Terraform change that waits for the owner.
- With #231–#234 this completes the Wave 6 "done when" path in code: an organization is
  created, connects a repo with its own token, is polled, and sees only its own data.
  Still owed: the GitHub App (needs the owner's account) and the web pages (cursor-agent).

## Addendum 4 (2026-11-27): GitLab, verified before building (#235)

Real anonymous calls to gitlab.com on 2026-11-27, against the public project
`inkscape/inkscape` (project 3472737, release milestones such as "Inkscape 1.5"):

| Data | REST v4, no token | GraphQL, no token |
|---|---|---|
| Merge requests (state, dates, milestone, labels, description) | 200 | 200 |
| MR approvals (`approved_by`, rules) | 200 | 200 (`approvedBy`) |
| MR pipelines, project pipelines (status, sha, ref) | 200 | not checked |
| Issues with milestone (title, state, dates, description) | 200 | 200 |
| Group milestones with start and due dates | not checked | 200 (`includeDescendants`) |
| Project milestones list | **401** | empty (Inkscape's are group milestones) |
| MR / issue notes and discussions | **401** | 200, system notes included ("approved this merge request", "requested review from ...") |
| Milestone and label history (`resource_milestone_events`, `resource_label_events`, `resource_state_events`) | **401** | not in system notes: 0 milestone and 0 label notes in 532 system notes over 50 issues and 30 MRs |

Rate limit, from the response headers: `throttle_unauthenticated_api`, 500 requests per
window, with `ratelimit-remaining` and `ratelimit-reset` exposed, so backoff can follow the
headers. GitLab's terms let you read public projects through the API. Contributor
usernames come back, as on GitHub: they would be stored for computation only and never
shown (CLAUDE.md section 10).

**What this means:**
- **Review flow works without a token.** Review rounds come from the review requests and
  approvals in the system notes, plus approvals and pipelines. Time to first review and
  review depth can be computed as for GitHub.
- **Release membership history does not.** Without `resource_milestone_events`, an issue
  that was in a milestone and was moved out cannot be found. CLAUDE.md section 6 requires
  discovering every item that was ever in a release, and backtests need history. Current
  state only would repeat the mistake the GraphQL timeline rule fixed on GitHub.
- **A read-only token fixes it.** A personal access token with `read_api` from any free
  gitlab.com account makes the resource-event endpoints readable for public projects.
  Not verified yet, because it needs an account.

**Decision:** build the GitLab collector after a `read_api` token exists (owner, one free
account, stored as a secret reference). It would use GraphQL for nested data and REST
resource events for history, through the shared HTTP client. Until then nothing is built
on partial data, and #235 waits on that one input. The proof dataset is `inkscape/inkscape`,
with group milestones as releases and MRs that close issues as links.
