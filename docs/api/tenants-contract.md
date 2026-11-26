# Tenants, members and connectors: API contract (Wave 6)

Decisions: ADR-0034 (tenants and isolation) and ADR-0035 (connector framework). Status:
**contract first**. The routes below are built in #231, #233 and #234. Until then they
return 404.

## Picking the tenant

- Header **`X-TPM-Tenant: <tenant_id>`** on every request the web server forwards. Leave it
  out for the public demo (`demo`), which is what every request does today.
- **Signature v2** adds the tenant as a sixth line of the HMAC message:

  ```
  user \n time \n METHOD \n path \n sha256(body) \n tenant
  ```

  Send `X-TPM-Signature-Version: 2` with it. Version 1 (five lines, no header) is accepted
  only for `demo`.
- Responses:

| Case | Status |
| --- | --- |
| `demo` (public), anyone | 200, as today |
| Another tenant, not signed in | 401 |
| Another tenant, signed in, not a member | 404 (the tenant's existence is not revealed) |
| Unknown tenant | 404 |
| Tenant store unreachable | 503 (never a fallback to `demo`) |
| Member, but the action needs a higher role | 403 |

## Roles

| Role | Can |
| --- | --- |
| `reader` | See the tenant's data |
| `approver` | Also everything that needs an approver today (exec updates, link and RAID decisions, readiness calls, paid AI) |
| `owner` | Also members, connectors, limits, export, deletion |

For `demo`, the `APPROVERS` allowlist still makes approvers. No one is an owner of `demo`
through the API.

## Routes

All routes need a signed-in user. Logins appear only in member management, which only the
tenant's owners can see.

### `GET /me/tenants`

The tenants the signed-in user belongs to, plus `demo`.

```json
{
  "tenants": [
    {"id": "demo", "name": "Public demo", "role": "reader", "public": true},
    {"id": "acme", "name": "Acme", "role": "owner", "public": false}
  ],
  "can_create": false
}
```

`can_create` is true only for logins in `TENANT_CREATORS` until sign-up opens (owner decision).

### `POST /tenants`

Body `{"id": "acme", "name": "Acme"}`. The id is 3-32 characters of `a-z0-9-`, and `demo`
and `system` are reserved. The creator becomes the owner. 201 returns the tenant; 409 if the
id is taken; 403 if `can_create` is false.

### `GET /tenants/{id}/members` (owner), `PUT /tenants/{id}/members/{login}` (owner), `DELETE /tenants/{id}/members/{login}` (owner)

`PUT` body: `{"role": "reader" | "approver" | "owner"}`. A tenant always keeps at least one
owner: removing or demoting the last one returns 409.

```json
{"members": [{"login": "octocat", "role": "owner", "added_at": "2026-11-27T10:00:00Z"}]}
```

### `GET /tenants/{id}/connectors` (member), `PUT /tenants/{id}/connectors/{team_id}` (owner), `DELETE ...` (owner)

- `PUT` body: the same object as a `connectors/teams/<id>.yaml` file, as JSON.
- 422 returns the schema errors.
- Secrets are references, for example `"token_ref": "github-token"`. The response says
  whether each reference resolves, and never shows a value:

```json
{
  "connectors": [
    {"team_id": "acme-web", "version": 3, "updated_at": "2026-11-27T10:05:00Z",
     "config": {"id": "acme-web", "display_name": "Acme web", "project": "acme-web", "...": "..."},
     "secrets": [{"ref": "github-token", "name": "tenant-acme-github-token", "found": true}]}
  ]
}
```

### `GET /tenants/{id}/limits` (member), `PUT /tenants/{id}/limits` (owner)

```json
{"ai_daily_budget_usd": 0.5, "ai_spent_today_usd": 0.12, "max_teams": 3, "teams": 1}
```

### `GET /tenants/{id}/audit` (owner)

Newest first, paged with `?before=<id>`. `actor` is the role at the time, not the login.

```json
{"entries": [{"id": 41, "at": "2026-11-27T10:05:00Z", "actor": "owner",
              "action": "connector_changed", "target": "acme-web", "details": {"version": 3}}]}
```

### `POST /tenants/{id}/export` (owner)

Returns `application/x-ndjson`: one line per row, `{"table": "...", "row": {...}}`, holding
only this tenant's rows.

### `DELETE /tenants/{id}` (owner)

Body `{"confirm": "<tenant id>"}`. Deletes every row the tenant owns, then the tenant, in one
transaction, and asks Secret Manager to delete `tenant-<id>-*`. 204 on success. `demo`
returns 403.
