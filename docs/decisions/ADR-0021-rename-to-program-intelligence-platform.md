# ADR-0021: Rename to Program Intelligence Platform

- **Status:** accepted (owner's decision, 2026-11-23)
- **Date:** 2026-11-23

## Context

The platform serves any cross-functional release program, not only TPMs, so the owner
renamed it from "TPM Intelligence" to **Program Intelligence Platform**. The old name is
in three kinds of places with very different costs to change:

1. **Display text:** the web app, README, CLAUDE.md, service titles, the team's display
   name. Labels only.
2. **The GitHub repository** `preetdhindsa1/tpm-intelligence`: the deploy identity
   (`infra/deploy.tf`, Workload Identity trusts that exact name), the webhook allowlist
   and the team files depend on it.
3. **The public URL**, which is the web Cloud Run service's name
   (`https://<name>-<project number>.<region>.run.app`).

## Decision

The owner chose layers 1 and 3 and kept layer 2:

- **Layer 1 (this change):** every display name becomes "Program Intelligence
  Platform". The front page's "this project" card now matches the live project through
  one constant (`web/lib/teams.ts`), and a test checks it equals the team file's
  `display_name`. The card used to look for the old name by prefix.
- **Layer 3:** the web service becomes `program-intelligence-platform`, so the site is
  https://program-intelligence-platform-109199755245.us-central1.run.app.
  The old URL is removed, not redirected (owner's choice). The switch is ordered so the
  deploy workflow never runs against a missing service name: `gcloud run services
  update` would create an unmanaged one.

**Kept on purpose:**

| What | Why it keeps the old name |
|---|---|
| GitHub repo `tpm-intelligence` | Owner's choice; renaming needs a coordinated deploy-identity switch |
| GCP project ID `tpm-intelligence` | Google never allows a project ID to change |
| Stored project key `tpm-intelligence` (`tpm-intelligence:Phase 3`) | Every stored event carries it; changing it would orphan the data |
| Team file names, Terraform state bucket, internal services (`tpm-api`, `tpm-github-poller`, ...) | Renaming recreates infrastructure or breaks references for no visible gain |
| Past ADRs | They record what was true when written |
| Local folder and Docker Compose project | Compose names its network and database volume after the folder |

## Alternatives

- **Display name only (layer 1).** No risk, but the URL keeps the old name.
- **Everything, including the repo (layers 1-3).** Most consistent, but the repo rename
  needs the deploy identity to trust both names during the switch.
- **Redirect the old URL** instead of removing it: keeps shared links working at almost
  no cost. Not chosen by the owner.

## Trade-offs

- Old links to the site stop working after layer 3.
- GitHub sign-in fails between the URL switch and the owner updating the OAuth app's
  callback URL. Reading stays public.
- Internal names (`tpm-*`) and the repo still say "tpm". That is deliberate and recorded
  here, so it is not mistaken for something left over.
