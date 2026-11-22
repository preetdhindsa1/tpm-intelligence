# infra/: Google Cloud (Terraform)

Design: [ADR-0007](../docs/decisions/ADR-0007-cloud-run.md), sized by
[ADR-0017](../docs/decisions/ADR-0017-lean-cloud-deploy.md) (option B). Not applied yet.

| File | What |
|---|---|
| `main.tf` | APIs, Artifact Registry |
| `data.tf` | Cloud SQL Postgres 16 (`db-g1-small`) |
| `pubsub.tf` | `normalized-events`, `worker` subscription, dead-letter topic (5 attempts) |
| `run.tf` | Cloud Run: `tpm-api` (runs the event worker in-process) and `tpm-web` (services), `tpm-github-poller` and `tpm-migrate` (jobs); OTel Collector sidecars |
| `deploy.tf` | Workload Identity Federation for GitHub Actions (main branch only) and the deployer account |
| `scheduler.tf` | Poller every 5 minutes |
| `secrets.tf` | `database-url`, `github-token`, `anthropic-api-key`, sign-in secrets (generated and hand-added), collector config |
| `iam.tf` | One service account per workload, least privilege |
| `monitoring.tf` | Alerts: queue backlog, dead letters, poller failures |

## Check it

```bash
make tf-validate   # fmt + validate, in Docker
make tf-plan       # offline plan: placeholder project, dummy token, nothing contacted
```

CI runs the same checks. On 2026-11-22 the plan for option B showed **91 resources to add**, both offline and against the real project (read-only).
An offline plan shows the configuration is consistent. It does not show that a real apply
works: quotas, org policies and API enablement are untested.

## Deploy (option B, ADR-0017)

Sizing: one always-on API (1 vCPU / 4 GiB, runs the event worker), web scaling 0-4,
Cloud SQL `db-g1-small`, no Redis. **Estimated** ~$95-125/month (not a quote; the measured
bill replaces it). Set a budget alert on the billing account first (console: Billing ->
Budgets & alerts).

**One command:** `sh infra/first-deploy.sh --yes --with-local-secrets --seed-local-data`
runs every step below and skips what is already done. Seed only into a fresh database,
before any migration has run there. The manual steps are listed for reference.

1. `sh infra/bootstrap.sh tpm-intelligence`: creates the private, versioned state bucket.
2. Fill in `infra/terraform.tfvars` (gitignored; see the example). Then `make tf-real-plan`,
   and review the plan.
3. First apply, in two stages, because services need an image to exist:
   - `terraform apply -target=google_project_service.apis -target=google_artifact_registry_repository.images`
   - build and push `app:bootstrap` and `web:bootstrap` for `linux/amd64`. Bake in the API URL:
     `--build-arg NEXT_PUBLIC_API_URL=https://tpm-api-<number>.<region>.run.app`.
   - `terraform apply`.
4. The hand-made secrets start as the placeholder `unconfigured` (the code treats it as unset). Add the real values: `github-token` (read-only), `anthropic-api-key`, and
   `auth-github-id` / `auth-github-secret` from a GitHub OAuth app whose callback is
   `<web_url>/api/auth/callback/github`. Use
   `printf %s "$VALUE" | gcloud secrets versions add <name> --data-file=-`.
5. `gcloud run jobs execute tpm-migrate --region us-central1 --wait`, then load the data
   (public events; restore a dump into Cloud SQL, or run backfills).
6. Set the repository variables for `.github/workflows/deploy.yml`: `GCP_PROJECT_ID`,
   `GCP_PROJECT_NUMBER`, `GCP_REGION`, `GCP_WIF_PROVIDER`, `GCP_DEPLOYER` (Terraform
   outputs). From then on, a green CI on `main` deploys.

## If you apply it later

1. Copy `terraform.tfvars.example` to `terraform.tfvars` (gitignored) and fill it in.
2. Enable the commented GCS backend. State holds generated secrets, so lock the bucket down.
3. Run `terraform apply`. Then push the `app` and `web` images to the `image_registry` output.
4. Add the GitHub token: `printf %s "$TOKEN" | gcloud secrets versions add github-token --data-file=-`.
5. Run `gcloud run jobs execute tpm-migrate --wait`. Then set `cors_origins` to the `web_url` output and apply again.
