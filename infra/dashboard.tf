# SLO dashboard (CLAUDE.md section 9; issue #40). One page for the live targets:
# availability, event -> dashboard, freshness (poller runs), queue age, API and web health.
# AI spend has no metric yet and is not drawn (roadmap gap).

# Seconds from an event at the source (GitHub's clock) to the push to an open page, per
# push, from the API's "live update pushed" log line (P3-M5).
resource "google_logging_metric" "event_to_dashboard" {
  name   = "tpm/event_to_dashboard_seconds"
  filter = "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"${google_cloud_run_v2_service.api.name}\" AND jsonPayload.message=\"live update pushed\" AND jsonPayload.seconds_since_occurred>=0"
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "DISTRIBUTION"
    unit        = "s"
  }
  value_extractor = "EXTRACT(jsonPayload.seconds_since_occurred)"
  bucket_options {
    explicit_buckets {
      bounds = [1, 2, 5, 10, 20, 30, 60, 120, 300, 600]
    }
  }
}

locals {
  dashboard_tiles = [
    {
      title   = "Availability: uptime checks passing (fraction, by target)"
      filter  = "metric.type=\"monitoring.googleapis.com/uptime_check/check_passed\" resource.type=\"uptime_url\""
      aligner = "ALIGN_FRACTION_TRUE"
      reducer = "REDUCE_MEAN"
      group   = ["resource.label.host"]
    },
    {
      title   = "Event -> dashboard, p95 seconds (target < 30 s)"
      filter  = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.event_to_dashboard.name}\" resource.type=\"cloud_run_revision\""
      aligner = "ALIGN_PERCENTILE_95"
      reducer = "REDUCE_MAX"
      group   = []
    },
    {
      title   = "Poller runs by result (freshness target < 10 min)"
      filter  = "metric.type=\"run.googleapis.com/job/completed_execution_count\" resource.type=\"cloud_run_job\" resource.label.job_name=\"${google_cloud_run_v2_job.poller.name}\""
      aligner = "ALIGN_SUM"
      reducer = "REDUCE_SUM"
      group   = ["metric.label.result"]
    },
    {
      title   = "Event queue: oldest unacked event (seconds)"
      filter  = "metric.type=\"pubsub.googleapis.com/subscription/oldest_unacked_message_age\" resource.type=\"pubsub_subscription\" resource.label.subscription_id=\"${google_pubsub_subscription.worker.name}\""
      aligner = "ALIGN_MAX"
      reducer = "REDUCE_MAX"
      group   = []
    },
    {
      title   = "Requests by service and response class"
      filter  = "metric.type=\"run.googleapis.com/request_count\" resource.type=\"cloud_run_revision\""
      aligner = "ALIGN_RATE"
      reducer = "REDUCE_SUM"
      group   = ["resource.label.service_name", "metric.label.response_code_class"]
    },
    {
      title   = "Request latency p95 by service (ms)"
      filter  = "metric.type=\"run.googleapis.com/request_latencies\" resource.type=\"cloud_run_revision\""
      aligner = "ALIGN_PERCENTILE_95"
      reducer = "REDUCE_MAX"
      group   = ["resource.label.service_name"]
    },
  ]
}

resource "google_monitoring_dashboard" "slo" {
  dashboard_json = jsonencode({
    displayName = "TPM: SLOs (CLAUDE.md section 9)"
    gridLayout = {
      columns = "2" # Google stores it as a string; a number showed as drift
      widgets = [
        for t in local.dashboard_tiles : {
          title = t.title
          xyChart = {
            dataSets = [{
              plotType   = "LINE"
              targetAxis = "Y1" # Google's default; leaving it out showed as drift
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = t.filter
                  aggregation = merge(
                    {
                      alignmentPeriod    = "300s"
                      perSeriesAligner   = t.aligner
                      crossSeriesReducer = t.reducer
                    },
                    length(t.group) > 0 ? { groupByFields = t.group } : {}
                  )
                }
              }
            }]
          }
        }
      ]
    }
  })
  depends_on = [google_project_service.apis]
}
