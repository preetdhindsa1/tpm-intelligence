# Alerts from CLAUDE.md section 9 that apply in phase 1. Fact-checker removal rate and
# AI spend arrive with the phase-2 agents.

# Where alerts go. Until 2026-11-24 there was no channel at all, so alerts fired and
# notified nobody (issue #14). The address lives in terraform.tfvars, which is gitignored.
resource "google_monitoring_notification_channel" "email" {
  count        = var.alert_email == "" ? 0 : 1
  display_name = "TPM alerts by email"
  type         = "email"
  labels = {
    email_address = var.alert_email
  }
  depends_on = [google_project_service.apis]
}

locals {
  alert_channels = concat(
    var.alert_notification_channels,
    google_monitoring_notification_channel.email[*].id,
  )
}

resource "google_monitoring_alert_policy" "queue_backlog" {
  display_name = "TPM: event queue backlog growing"
  combiner     = "OR"

  conditions {
    # 3 min held for 2 min. The old 10 min held for 5 min opened 18 minutes after a real
    # backlog began (2026-11-24, 03:23 -> 03:41), far too late for a 30 s target. Batched
    # storing clears even the hourly Jira burst in well under a minute.
    display_name = "Oldest unacked event older than 3 minutes"
    condition_threshold {
      filter          = "resource.type = \"pubsub_subscription\" AND resource.labels.subscription_id = \"${google_pubsub_subscription.worker.name}\" AND metric.type = \"pubsub.googleapis.com/subscription/oldest_unacked_message_age\""
      comparison      = "COMPARISON_GT"
      threshold_value = 180
      duration        = "120s"
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MAX"
      }
    }
  }

  notification_channels = local.alert_channels
  depends_on            = [google_project_service.apis]
}

resource "google_monitoring_alert_policy" "dead_letters" {
  display_name = "TPM: events dead-lettered"
  combiner     = "OR"

  conditions {
    display_name = "Messages published to the dead-letter topic"
    condition_threshold {
      filter          = "resource.type = \"pubsub_topic\" AND resource.labels.topic_id = \"${google_pubsub_topic.events_dead_letter.name}\" AND metric.type = \"pubsub.googleapis.com/topic/send_message_operation_count\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_SUM"
      }
    }
  }

  notification_channels = local.alert_channels
  depends_on            = [google_project_service.apis]
}

# "2 failed polls in a row", approximated as 2 failed executions within 3 schedule periods.
# The exact consecutive count is in Postgres (sync_cursors.consecutive_failures).
resource "google_monitoring_alert_policy" "poller_failures" {
  display_name = "TPM: GitHub poller failing"
  combiner     = "OR"

  conditions {
    display_name = "2+ failed poller executions in 15 minutes"
    condition_threshold {
      filter          = "resource.type = \"cloud_run_job\" AND resource.labels.job_name = \"${google_cloud_run_v2_job.poller.name}\" AND metric.type = \"run.googleapis.com/job/completed_execution_count\" AND metric.labels.result = \"failed\""
      comparison      = "COMPARISON_GT"
      threshold_value = 1
      duration        = "0s"
      aggregations {
        alignment_period   = "900s"
        per_series_aligner = "ALIGN_SUM"
      }
    }
  }

  notification_channels = local.alert_channels
  depends_on            = [google_project_service.apis]
}

# AI spend at 80% of the daily cap (CLAUDE.md section 9). The gateway exports the
# ai.budget.used_fraction gauge; the collector sends it to Managed Prometheus.
# Google rejects a PromQL alert on a metric that has never been written, so this is off
# until the API has made at least one AI call: then set enable_ai_budget_alert = true
# (done 2026-11-24 in terraform.tfvars, #45: the metric exists in the live project).
resource "google_monitoring_alert_policy" "ai_budget" {
  count        = var.enable_ai_budget_alert ? 1 : 0
  display_name = "TPM: AI spend at 80% of the daily cap"
  combiner     = "OR"

  conditions {
    display_name = "ai_budget_used_fraction >= 0.8"
    condition_prometheus_query_language {
      query    = "max(ai_budget_used_fraction) >= 0.8"
      duration = "60s"
    }
  }

  notification_channels = local.alert_channels
  depends_on            = [google_project_service.apis]
}

# Unusual fact-checker removal rate (CLAUDE.md section 9; #45): mean share of claims
# removed per checked output, over an hour, above 30% (the redraft threshold).
resource "google_logging_metric" "claims_removal_rate" {
  name   = "tpm/claims_removal_rate"
  filter = "resource.type=\"cloud_run_revision\" AND jsonPayload.logger=\"agents.gateway\" AND jsonPayload.message=\"claims checked\" AND jsonPayload.claims>0"
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "DISTRIBUTION"
    unit        = "1"
  }
  value_extractor = "EXTRACT(jsonPayload.removal_rate)"
  bucket_options {
    linear_buckets {
      num_finite_buckets = 10
      width              = 0.1
      offset             = 0
    }
  }
}

resource "google_monitoring_alert_policy" "claims_removal_rate" {
  display_name = "TPM: fact checker removing an unusual share of claims"
  combiner     = "OR"
  conditions {
    display_name = "Mean removal rate over an hour above 30%"
    condition_threshold {
      filter          = "resource.type = \"cloud_run_revision\" AND metric.type = \"logging.googleapis.com/user/${google_logging_metric.claims_removal_rate.name}\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0.3
      duration        = "0s"
      aggregations {
        alignment_period     = "3600s"
        per_series_aligner   = "ALIGN_DELTA"
        cross_series_reducer = "REDUCE_MEAN"
      }
    }
  }
  notification_channels = local.alert_channels
  depends_on            = [google_project_service.apis]
}
