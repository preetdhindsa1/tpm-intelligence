# infra/: Google Cloud (Terraform, plan only in phase 1)

Nothing here has been applied. Design and trade-offs are in
[ADR-0007](../docs/decisions/ADR-0007-cloud-run.md).

| File | What |
|---|---|
| `main.tf` | APIs, Artifact Registry |
| `network.tf` | VPC + subnet (Memorystore, Cloud Run direct VPC egress) |
| `data.tf` | Cloud SQL Postgres 16, Memorystore Redis 7.2 |
| `pubsub.tf` | `normalized-events`, `worker` subscription, dead-letter topic (5 attempts) |
| `run.tf` | Cloud Run: `tpm-api`, `tpm-web` (services), `tpm-worker` (worker pool), `tpm-github-poller`, `tpm-migrate` (jobs); OTel Collector sidecars |
| `scheduler.tf` | Poller every 5 minutes |
| `secrets.tf` | `database-url`, `redis-url`, `github-token`, collector config |
| `iam.tf` | One service account per workload, least privilege |
| `monitoring.tf` | Alerts: queue backlog, dead letters, poller failures |

## Check it

```bash
make tf-validate   # fmt + validate, in Docker
make tf-plan       # offline plan: placeholder project, dummy token, nothing contacted
```

CI runs the same checks. On 2026-11-22 the offline plan showed **84 resources to add** (81 before the Phase 2 AI key secret and spend alert).
An offline plan shows the configuration is consistent. It does not show that a real apply
works: quotas, org policies and API enablement are untested.

## If you apply it later

1. Copy `terraform.tfvars.example` to `terraform.tfvars` (gitignored) and fill it in.
2. Enable the commented GCS backend. State holds generated secrets, so lock the bucket down.
3. Run `terraform apply`. Then push the `app` and `web` images to the `image_registry` output.
4. Add the GitHub token: `printf %s "$TOKEN" | gcloud secrets versions add github-token --data-file=-`.
5. Run `gcloud run jobs execute tpm-migrate --wait`. Then set `cors_origins` to the `web_url` output and apply again.
