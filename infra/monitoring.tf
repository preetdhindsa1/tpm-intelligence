# Alerts from CLAUDE.md section 9 that apply in phase 1. Fact-checker removal rate and
# AI spend arrive with the phase-2 agents.

resource "google_monitoring_alert_policy" "queue_backlog" {
  display_name = "TPM: event queue backlog growing"
  combiner     = "OR"

  conditions {
    display_name = "Oldest unacked event older than 10 minutes"
    condition_threshold {
      filter          = "resource.type = \"pubsub_subscription\" AND resource.labels.subscription_id = \"${google_pubsub_subscription.worker.name}\" AND metric.type = \"pubsub.googleapis.com/subscription/oldest_unacked_message_age\""
      comparison      = "COMPARISON_GT"
      threshold_value = 600
      duration        = "300s"
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MAX"
      }
    }
  }

  notification_channels = var.alert_notification_channels
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

  notification_channels = var.alert_notification_channels
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

  notification_channels = var.alert_notification_channels
  depends_on            = [google_project_service.apis]
}
