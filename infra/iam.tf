# One service account per workload, least privilege (CLAUDE.md section 10).

locals {
  service_accounts = {
    api       = "TPM API (read DB, live updates; runs the event worker in-process, ADR-0017)"
    poller    = "TPM GitHub poller (read-only GitHub, publish events)"
    migrate   = "TPM database migrations"
    web       = "TPM web app"
    scheduler = "Cloud Scheduler: start the poller job"
  }

  # Every Python service exports traces, metrics and logs through its collector sidecar.
  telemetry_roles = ["roles/cloudtrace.agent", "roles/monitoring.metricWriter", "roles/logging.logWriter"]
  db_users        = ["api", "poller", "migrate"]

  telemetry_bindings = {
    for pair in setproduct(local.db_users, local.telemetry_roles) : "${pair[0]}:${pair[1]}" => {
      sa   = pair[0]
      role = pair[1]
    }
  }
}

resource "google_service_account" "sa" {
  for_each     = local.service_accounts
  account_id   = "${local.name}-${each.key}"
  display_name = each.value
}

resource "google_project_iam_member" "telemetry" {
  for_each = local.telemetry_bindings
  project  = var.project_id
  role     = each.value.role
  member   = google_service_account.sa[each.value.sa].member
}

resource "google_project_iam_member" "cloudsql_client" {
  for_each = toset(local.db_users)
  project  = var.project_id
  role     = "roles/cloudsql.client"
  member   = google_service_account.sa[each.key].member
}

# Scheduler may start the poller job and nothing else.
resource "google_cloud_run_v2_job_iam_member" "scheduler_runs_poller" {
  name     = google_cloud_run_v2_job.poller.name
  location = var.region
  role     = "roles/run.invoker"
  member   = google_service_account.sa["scheduler"].member
}
