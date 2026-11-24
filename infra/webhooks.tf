# GitHub webhook receiver (P3-M5, ADR-0020): a public, scale-to-zero Cloud Run service.
# Every request must carry a valid X-Hub-Signature-256; the receiver publishes normalized
# events to Pub/Sub, where the API's in-process worker stores them (ADR-0017).

locals {
  webhook_url = "https://${local.name}-webhooks-${var.project_number}.${var.region}.run.app"
}

resource "google_service_account" "webhooks" {
  account_id   = "${local.name}-webhooks"
  display_name = "TPM webhook receiver (verify signatures, publish events)"
}

resource "google_project_iam_member" "webhooks_telemetry" {
  for_each = toset(local.telemetry_roles)
  project  = var.project_id
  role     = each.value
  member   = google_service_account.webhooks.member
}

# Generated here; the owner pastes it into the GitHub App's webhook settings:
#   gcloud secrets versions access latest --secret github-webhook-secret
resource "random_password" "webhook" {
  length  = 48
  special = false
}

resource "google_secret_manager_secret" "github_webhook" {
  secret_id = "github-webhook-secret"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "github_webhook" {
  secret      = google_secret_manager_secret.github_webhook.id
  secret_data = random_password.webhook.result
}

resource "google_secret_manager_secret_iam_member" "webhooks_reads" {
  for_each = {
    webhook     = google_secret_manager_secret.github_webhook.id
    github      = google_secret_manager_secret.github_token.id # planning-issue timelines
    otel_config = google_secret_manager_secret.otel_config.id
  }
  secret_id = each.value
  role      = "roles/secretmanager.secretAccessor"
  member    = google_service_account.webhooks.member
}

resource "google_pubsub_topic_iam_member" "webhooks_publish" {
  topic  = google_pubsub_topic.events.id
  role   = "roles/pubsub.publisher"
  member = google_service_account.webhooks.member
}

resource "google_cloud_run_v2_service" "webhooks" {
  name                = "${local.name}-webhooks"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account = google_service_account.webhooks.email
    timeout         = "30s" # GitHub gives up after 10 s

    scaling {
      # One warm instance: a cold start took 12.1 s on GitHub's first ping (2026-11-23),
      # past GitHub's 10 s limit. With cpu_idle it is billed at the idle rate between events.
      min_instance_count = 1
      max_instance_count = 2
    }

    containers {
      name    = "webhooks"
      image   = local.app_image
      command = ["python", "-m", "collectors.github_webhooks"]

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        cpu_idle          = true
        startup_cpu_boost = true # shorter cold starts inside GitHub's 10 s limit
      }

      dynamic "env" {
        for_each = merge(local.common_env, {
          OTEL_SERVICE_NAME = "tpm-webhooks"
          # CPU is throttled between requests (cpu_idle), so background exports time out.
          # Each delivery flushes telemetry before answering; this only catches stragglers.
          OTEL_METRIC_EXPORT_INTERVAL = "3600000"
        })
        content {
          name  = env.key
          value = env.value
        }
      }
      env {
        name = "GITHUB_WEBHOOK_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.github_webhook.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "GITHUB_TOKEN"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.github_token.secret_id
            version = "latest"
          }
        }
      }

      startup_probe {
        http_get {
          path = "/health"
        }
        period_seconds    = 1
        failure_threshold = 20
      }
    }

    containers {
      name  = "otel-collector"
      image = local.otel_image
      args  = ["--config=/etc/otelcol/config.yaml"]
      resources {
        limits = {
          cpu    = "0.5"
          memory = "256Mi"
        }
        # Match the receiver (Cloud Run sets these on every container; leaving them unset
        # here showed as drift on every plan).
        cpu_idle          = true
        startup_cpu_boost = true
      }
      volume_mounts {
        name       = "otel-config"
        mount_path = "/etc/otelcol"
      }
    }

    volumes {
      name = "otel-config"
      secret {
        secret = google_secret_manager_secret.otel_config.secret_id
        items {
          version = "latest"
          path    = "config.yaml"
        }
      }
    }
  }

  # The deploy workflow rolls out new images; Terraform owns everything else.
  lifecycle {
    ignore_changes = [template[0].containers[0].image, client, client_version]
  }

  depends_on = [
    google_secret_manager_secret_iam_member.webhooks_reads,
    google_secret_manager_secret_version.github_webhook,
    google_secret_manager_secret_version.otel_config,
    google_secret_manager_secret_version.placeholder,
  ]
}

# Public: GitHub must reach it. The signature check is the gate.
resource "google_cloud_run_v2_service_iam_member" "webhooks_public" {
  name     = google_cloud_run_v2_service.webhooks.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_service_account_iam_member" "deployer_acts_as_webhooks" {
  service_account_id = google_service_account.webhooks.name
  role               = "roles/iam.serviceAccountUser"
  member             = google_service_account.deployer.member
}

# Rejected signatures: someone is probing the endpoint, or the secret is out of sync.
resource "google_logging_metric" "webhook_bad_signature" {
  name   = "tpm/webhook_bad_signature"
  filter = "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"${google_cloud_run_v2_service.webhooks.name}\" AND jsonPayload.message=\"webhook signature rejected\""
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
  }
}

resource "google_monitoring_alert_policy" "webhook_bad_signature" {
  display_name = "TPM: webhook signatures rejected"
  combiner     = "OR"

  conditions {
    display_name = "More than 20 rejected webhook signatures in 10 minutes"
    condition_threshold {
      filter          = "resource.type = \"cloud_run_revision\" AND metric.type = \"logging.googleapis.com/user/${google_logging_metric.webhook_bad_signature.name}\""
      comparison      = "COMPARISON_GT"
      threshold_value = 20
      duration        = "0s"
      aggregations {
        alignment_period   = "600s"
        per_series_aligner = "ALIGN_SUM"
      }
    }
  }

  notification_channels = local.alert_channels
}
