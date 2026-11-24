# Runbook

How to operate the live deployment (ADR-0017): where to look, how changes ship, and what to
do when an alert fires. Written from real incidents; add to it after each new one.

Project `tpm-intelligence`, region `us-central1`. Commands assume `gcloud` is signed in to
that project.

## Where to look

| What | Where |
|---|---|
| Alerts and incidents | https://console.cloud.google.com/monitoring/alerting?project=tpm-intelligence |
| Services (web, API, webhooks) | https://console.cloud.google.com/run?project=tpm-intelligence |
| Poller runs (every 5 min) | https://console.cloud.google.com/run/jobs/details/us-central1/tpm-github-poller/executions?project=tpm-intelligence |
| Jira collector runs (hourly, Kafka plan) | https://console.cloud.google.com/run/jobs/details/us-central1/tpm-jira-collector/executions?project=tpm-intelligence |
| Errors | https://console.cloud.google.com/logs/query;query=severity%3E%3DERROR?project=tpm-intelligence |
| Traces | https://console.cloud.google.com/traces/list?project=tpm-intelligence |
| CI and deploys | https://github.com/preetdhindsa1/tpm-intelligence/actions |
| Webhook deliveries | Repository Settings → Webhooks → Recent Deliveries |

Alerts email the owner (notification channel from `alert_email` in the gitignored
`infra/terraform.tfvars`, #14).

## How changes ship

- **Code:** merge to `main` → CI → the Deploy workflow builds images and rolls them out
  to the API, web, webhook receiver, poller job and Jira collector job.
- **Infrastructure:** the Deploy workflow does **not** apply Terraform. Apply by hand,
  then record the change in a PR:
  ```
  cd infra
  terraform plan -out=x.tfplan     # read it: only the intended resources?
  terraform apply x.tfplan
  terraform plan -detailed-exitcode # 0 = code and cloud match
  ```
  Terraform runs in Docker on the owner's machine (`hashicorp/terraform:1.10` with
  `GOOGLE_OAUTH_ACCESS_TOKEN=$(gcloud auth print-access-token)`).
- **Order matters** when code and infrastructure change together: deploy the image first
  if new arguments need new code (the poller's `--poll` option, P3-M5).
- **Renaming the web service** changes the public URL: see ADR-0021 for the safe order
  (`gcloud run services update` creates a service that does not exist).

## Rollback

- **Code:** route traffic back to the previous revision, then revert the merge on `main`:
  ```
  gcloud run revisions list --service tpm-api --region us-central1
  gcloud run services update-traffic tpm-api --region us-central1 --to-revisions <previous>=100
  ```
  Same for `program-intelligence-platform` (web) and `tpm-webhooks`. For the poller job,
  `gcloud run jobs update tpm-github-poller --region us-central1 --image <previous image>`.
- **Infrastructure:** revert the Terraform change in a PR and apply it.

## Alerts

### TPM: GitHub poller failing (2+ failed runs in 15 minutes)

1. Open the poller runs page; check the latest run's logs for `stream failed`. The
   `stream` field says which team and stream; `exception` has the error.
2. Seen so far:
   - `No such file or directory` on `/cloudsql/...`: the job lost its Cloud SQL socket
     (sidecar container setup). Fixed by running it as one container (2026-11-23).
   - Memory under 512 Mi rejected: gen2 jobs need at least 512 Mi (2026-11-23).
   - `git/trees/master -> 404`: a team without KEP specs was asked for them (#11).
   - HTTP 403/429 from GitHub: token expired or rate-limited; check the `github-token`
     secret and the rate-limit headers in the logs.
3. Webhooks keep delivering this repository's events during a poller outage; Kubernetes
   data goes stale (freshness SLO 10 min).
4. Run once by hand after a fix:
   `gcloud run jobs execute tpm-github-poller --region us-central1 --wait`.

### TPM: webhook signatures rejected (more than 20 in 10 minutes)

- Someone is probing the endpoint, or the webhook secret and GitHub's copy differ.
- Check Recent Deliveries on GitHub: if GitHub's own deliveries fail with 401, re-copy the
  secret (`github-webhook-secret` in Secret Manager) into the webhook settings.
- The deploy workflow's smoke test sends one unsigned request per deploy (expected 401).

### TPM: event queue backlog growing (oldest unacked event over 10 minutes)

- The API's in-process worker is not consuming. Check `tpm-api` logs for
  `in-process worker failed` and that the latest revision is serving.
- After a deploy, the old revision lives up to about 2 minutes (open live pages) and
  hands back unprocessed messages on shutdown (P3-M5). Longer backlogs are not that.

### TPM: events dead-lettered

- An event failed 5 times and moved to `normalized-events-dead-letter`. Check `tpm-api` logs for
  `dead-lettering message after repeated failures`, fix the cause, then replay from the
  dead-letter subscription.

### TPM: web is down / TPM: api is down (uptime check failing from 2+ regions)

1. Open the service in Cloud Run: is the latest revision ready? Recent deploy?
2. Roll back (above) if a deploy broke it.
3. The API needs Cloud SQL: check the instance is running.

## Known behaviours (not incidents)

- A recompute after new data touches a finished release rebuilds the calibration
  (~35-40 s once); others take about 5-10 s (ADR-0019).
- Live pages reconnect every 2 minutes and refresh if data changed meanwhile.
- The poller republishes facts it has already seen; the worker stores each once
  (duplicates are logged at debug level only).
