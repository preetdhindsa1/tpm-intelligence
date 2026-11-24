# Security review: public endpoints

- **Date:** 2026-11-24 (P3-M6, issue #64)
- **Scope:** the live site, API and webhook receiver (ADR-0017), as an unauthenticated
  visitor would reach them. Checked against the running deployment, not only the code.
- **Out of scope:** Google Cloud's own controls, GitHub's OAuth, and a full penetration test.

## What was checked and how

| Area | How | Result |
|---|---|---|
| Write actions (create, edit, approve or reject an update; save a scenario; decide a link) | Unauthenticated `POST`/`PATCH` to the live API | ✅ All refused with 401. Actions need a GitHub sign-in on the approver allowlist and a request signed by the web server (ADR-0016) |
| Paid AI | Anonymous `GET` of a risk note | ✅ Returns the stored note only; generating a new one needs an approver |
| Sign-in cookies | Response headers of `/api/auth/csrf` | ✅ `__Host-` / `__Secure-` prefixes, `Secure`, `HttpOnly`, `SameSite=Lax` |
| CORS | `Origin` header tests against the API | ✅ Only the site's own origin is allowed |
| Webhooks | Code and live tests (#14 alert test) | ✅ HMAC-SHA256 checked in constant time, unsigned requests get 401, payloads capped at 5 MB, only listed repositories accepted, repeated deliveries ignored |
| Secrets | Repository, CI, infrastructure | ✅ Secret Manager in the cloud, gitignored `.env` and `terraform.tfvars`, gitleaks in CI over the full history, read-only data tokens |
| Dependencies | CI | ✅ pip-audit and npm audit on every change; Dependabot weekly (#18, #34) |
| Web security headers | Live response headers | ❌ None: no HSTS, no framing protection, no `nosniff`; `X-Powered-By: Next.js` exposed |
| API security headers | Live response headers | ❌ No `nosniff` or framing protection |
| Capacity abuse: live streams | Cloud Run settings | ❌ One API instance (ADR-0017) takes 160 concurrent requests; each open live page holds one, so about 160 open pages would block the site |
| Capacity abuse: simulator | Code | ❌ Public and CPU-heavy, no limit on parallel runs. Inputs and replications are bounded, so one request cannot be made expensive; many at once could tie up the instance |
| Content-Security-Policy | Live response headers | ✅ Since #65: per-request nonce, `strict-dynamic`, no `unsafe-inline` for scripts |

## Fixed in this change (#64)

- **Web:** `Strict-Transport-Security`, `X-Frame-Options: DENY` (the approve pages cannot
  be framed), `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Permissions-Policy`;
  `X-Powered-By` removed.
- **API:** `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer` on every response.
- **Live streams:** at most 100 open at once; more get 503 with `Retry-After: 30` (browsers
  retry by themselves). Streams already end every 2 minutes (ADR-0022).
- **Simulator:** at most 2 runs at once; more get 429 with `Retry-After: 5`.

## Follow-ups

- **#65** Content-Security-Policy (done): `web/proxy.ts` sets a fresh nonce per request, so
  only Next.js's own scripts run. Checked locally in headless Chrome with the policy
  enforced: 10 pages, 0 violations, live updates connected; an injected `onerror` handler
  and inline script were blocked (the same page without the policy ran them).
  `CSP_MODE=report-only` relaxes it without a code change if a page breaks.
- **#66** The risk-note page took 12.5 s for a stored note (performance, found during the
  review).
- No per-IP rate limiting beyond the limits above. Reads are public by design; Cloud Run's
  request limits and the single instance bound the cost.
