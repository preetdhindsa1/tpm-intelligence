# Starts the poller job on a schedule (Cloud Run Admin API "run" call).

resource "google_cloud_scheduler_job" "poll" {
  name      = "${local.name}-poll-github"
  region    = var.region
  schedule  = var.poll_schedule
  time_zone = "Etc/UTC"

  retry_config {
    retry_count = 0 # the next scheduled run is the retry; failures feed the alert below
  }

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.poller.name}:run"

    oauth_token {
      service_account_email = google_service_account.sa["scheduler"].email
    }
  }

  depends_on = [google_project_service.apis]
}
