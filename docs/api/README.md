# API contracts

The FastAPI service documents every endpoint at `/docs` (OpenAPI). This folder holds the
contracts written **before** a screen is built, with exact JSON examples, so the web app and
the API can be built in parallel (`docs/plan/e2e-plan.md`, "Contract first").

| File | Endpoints | Rules |
|---|---|---|
| [`ux-v1-contract.md`](ux-v1-contract.md) | `GET /portfolio`; `pod` on `GET /lab` | ADR-0025; ADR-0023 addendum 2 |
| [`raid-contract.md`](raid-contract.md) | `GET /raid`, `/raid/queue`, `/raid/summary`, `/raid/{item_id}/history`; `POST /raid/{item_id}/confirm`, `/edit`, `/reject` | ADR-0030 (Wave 4) |
| [`readiness-retro-contract.md`](readiness-retro-contract.md) | `GET /readiness`, `POST /readiness/{release}/decision`; `GET /retro`, `/retro/said-vs-showed`, `/retro/patterns`, `/retro/lanes`; `GET /results` | ADR-0032 (Wave 5) |

A contract changes only with a new version of its file. The live numbers move; the shape does not.
