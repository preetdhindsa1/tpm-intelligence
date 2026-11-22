# ADR-0016: Sign-in with GitHub, signed actions and an approver allowlist

- **Status:** accepted (Phase 3 M1)
- **Date:** 2026-11-22

## Context

Before a public deploy (Phase 3 M2), anyone who could reach the app could:
- draft an executive update (paid AI);
- edit, approve or reject one;
- confirm or reject AI link suggestions (which change the facts and the forecast);
- save scenarios;
- trigger a paid risk note by opening a feature page.

Every decision was recorded as "<APPROVER_NAME> (local, unauthenticated)".
CLAUDE.md requires that humans approve, and that the platform never sends anything itself.

## Decision

- **Reading stays public; acting needs an approver.** The protected actions are:
  - drafting, editing, approving and rejecting executive updates;
  - confirming and rejecting link suggestions;
  - saving scenarios;
  - **generating** a risk note.

  Anyone sees stored risk notes. A visitor who is not an approver never triggers Claude,
  and sees "sign in as an approver to generate". Running a scenario without saving it
  stays public: CPU only, nothing stored, no AI.
- **Sign-in with GitHub** in the web app with next-auth 4.24 (stable; Auth.js v5 is still
  beta). It requests `read:user` only, and the session carries the GitHub login.
- **Signed forwarding.** The browser calls a same-origin route, `/api/act/...`. The web
  server adds `X-TPM-User`, `X-TPM-Time` and `X-TPM-Signature`: HMAC-SHA256 over the user,
  time, method, path with query, and the SHA-256 of the body, using a secret shared
  only by web and API (`TPM_ACTION_SECRET`). The API rejects signatures older than 5
  minutes, a changed path or body, and logins not on `APPROVERS`. The API is the only
  place that enforces permissions. The UI asks `GET /me` only to decide which buttons to
  enable.
- **Identity on records.** Decisions record `user:<github-login>`.
- **Fail closed.** `AUTH_MODE=required` is the default.
  - With no secret, every action is refused.
  - `AUTH_MODE=local` is for a laptop only: unsigned requests act as "local", recorded
    as `user:local (local, unauthenticated)`. Signed requests are still verified.
  - A "sign in as" development login exists only when `AUTH_DEV_LOGIN=true` **and**
    `AUTH_MODE=local`, so it cannot be turned on in a deployment that enforces sign-in.

## Alternatives

- **API verifies the next-auth session cookie or JWT itself.** It would couple the API to
  next-auth's token format and put a session secret in two services anyway.
- **API calls GitHub to check an OAuth token on each request.** It adds GitHub latency
  and rate limits to every action, and exposes the token to the browser.
- **Browser calls the API directly with a bearer token.** The token would then live in
  the browser.

## Trade-offs

- The allowlist is configuration, not a UI: changing approvers means changing
  `APPROVERS` and restarting.
- No per-team data isolation yet: all data is public (Kubernetes, Apache Kafka). A
  private team repo would need a check that the signed-in user can read it on GitHub
  (CLAUDE.md section 10). Planned with the first private connector.
- Signatures are replayable within 5 minutes for the same method, path and body. The
  forwarding happens server to server, and the actions are idempotent or refuse a
  second decision (409).

## Tested

- API: every protected endpoint returns 401 to anonymous requests and 403 to a signed-in
  non-approver. Wrong secret, expired, other-path and changed-body signatures are
  refused. No secret fails closed. Approval records `user:preetdhindsa1`. Anonymous risk
  notes never call AI.
- Web: the signature matches the Python implementation (known-answer test). Path
  checks, and the development login is only on in local mode.
- Browser (2026-11-22, API in required mode, development login):
  - anonymous: Draft disabled, action 401;
  - `someone-else`: Draft disabled, action 403;
  - `preetdhindsa1`: Draft enabled, action passes sign-in.

  A real GitHub sign-in is TBD until the OAuth app exists.
