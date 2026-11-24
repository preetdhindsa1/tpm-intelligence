# Availability (CLAUDE.md section 9: 99.5%). Uptime checks from several regions every
# 5 minutes; an alert when a check fails from 2+ regions for 5 minutes (issue #36).
# Cloud Run reserves public paths ending in "z", so the API is checked at /health.

locals {
  uptime_targets = {
    web = { host = replace(local.web_url, "https://", ""), path = "/" }
    api = { host = replace(local.api_url, "https://", ""), path = "/health" }
  }
}

resource "google_monitoring_uptime_check_config" "site" {
  for_each     = local.uptime_targets
  display_name = "TPM: ${each.key} is up"
  timeout      = "10s"
  period       = "300s"

  http_check {
    path           = each.value.path
    port           = 443
    use_ssl        = true
    validate_ssl   = true
    request_method = "GET"
    accepted_response_status_codes {
      status_class = "STATUS_CLASS_2XX"
    }
  }

  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = var.project_id
      host       = each.value.host
    }
  }

  depends_on = [google_project_service.apis]
}

resource "google_monitoring_alert_policy" "site_down" {
  for_each     = local.uptime_targets
  display_name = "TPM: ${each.key} is down"
  combiner     = "OR"

  conditions {
    display_name = "Uptime check failing from 2+ regions for 5 minutes"
    condition_threshold {
      filter          = "resource.type = \"uptime_url\" AND metric.type = \"monitoring.googleapis.com/uptime_check/check_passed\" AND metric.labels.check_id = \"${google_monitoring_uptime_check_config.site[each.key].uptime_check_id}\""
      comparison      = "COMPARISON_GT"
      threshold_value = 1
      duration        = "300s"
      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_NEXT_OLDER"
        cross_series_reducer = "REDUCE_COUNT_FALSE"
        group_by_fields      = ["resource.label.host"]
      }
    }
  }

  notification_channels = local.alert_channels
  depends_on            = [google_project_service.apis]
}
