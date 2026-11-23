# Cloud Run workloads (ADR-0007, sized for option B in ADR-0017). One Python image
# (Dockerfile) with a different command per workload. The API also runs the event worker. Each Python workload runs the OTel Collector
# as a sidecar on localhost:4317, exporting to Cloud Trace / Monitoring / Logging.

locals {
  common_env = {
    DEPLOY_ENV                  = "cloud"
    LOG_LEVEL                   = "INFO"
    QUEUE_BACKEND               = "pubsub"
    PUBSUB_PROJECT_ID           = var.project_id
    OTEL_EXPORTER_OTLP_ENDPOINT = "http://localhost:4317"
    OTEL_EXPORTER_OTLP_INSECURE = "true"
  }

}

# ---------------------------------------------------------------- API (FastAPI + SSE)

resource "google_cloud_run_v2_service" "api" {
  name                = "${local.name}-api"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account = google_service_account.sa["api"].email
    timeout         = "3600s" # SSE streams stay open

    scaling {
      # Exactly one instance: it holds the computed release in memory and runs the only
      # event worker, whose live-update notices reach SSE clients of this instance only.
      min_instance_count = 1
      max_instance_count = 1
    }


    containers {
      name    = "api"
      image   = local.app_image
      command = ["python", "-m", "api.main"]

      ports {
        container_port = 8000
      }

      resources {
        limits = {
          cpu = "1"
          # The computed release is ~1.4 GiB, and a background recompute briefly holds a
          # second copy (stale-while-revalidate, ADR-0002), so 2 GiB would run out.
          memory = "4Gi"
        }
        cpu_idle = false # recompute, the worker and SSE pushes happen outside requests
      }

      dynamic "env" {
        for_each = merge(local.common_env, {
          OTEL_SERVICE_NAME = "tpm-api"
          CORS_ORIGINS      = join(",", concat([local.web_url], var.cors_origins))
          WORKER_IN_PROCESS = "true"
          AUTH_MODE         = "required" # ADR-0016: fail closed
          APPROVERS         = join(",", var.approvers)
        })
        content {
          name  = env.key
          value = env.value
        }
      }
      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.database_url.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "TPM_ACTION_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.generated["tpm-action-secret"].secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "ANTHROPIC_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.anthropic_api_key.secret_id
            version = "latest"
          }
        }
      }

      startup_probe {
        http_get {
          path = "/healthz"
        }
        period_seconds    = 5
        failure_threshold = 24
      }

      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
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
      }
      volume_mounts {
        name       = "otel-config"
        mount_path = "/etc/otelcol"
      }
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.db.connection_name]
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
    google_secret_manager_secret_iam_member.readers,
    google_secret_manager_secret_version.otel_config,
    google_secret_manager_secret_version.placeholder,
    # Cloud Run refuses a secret with no version; this one waits for Cloud SQL.
    google_secret_manager_secret_version.database_url,
  ]
}

# ---------------------------------------------------------------- Web (Next.js)

resource "google_cloud_run_v2_service" "web" {
  name                = "${local.name}-web"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account = google_service_account.sa["web"].email

    scaling {
      min_instance_count = 0
      max_instance_count = 4
    }

    containers {
      image = local.web_image
      ports {
        container_port = 3000
      }
      # Server-side rendering calls the API over HTTPS. The browser's SSE URL
      # (NEXT_PUBLIC_API_URL) is baked in at image build time (deploy workflow).
      dynamic "env" {
        for_each = {
          API_URL      = local.api_url
          NEXTAUTH_URL = local.web_url
          AUTH_MODE    = "required" # never enables the development login (ADR-0016)
        }
        content {
          name  = env.key
          value = env.value
        }
      }
      dynamic "env" {
        for_each = {
          TPM_ACTION_SECRET  = google_secret_manager_secret.generated["tpm-action-secret"].secret_id
          AUTH_SECRET        = google_secret_manager_secret.generated["auth-secret"].secret_id
          AUTH_GITHUB_ID     = google_secret_manager_secret.github_oauth["auth-github-id"].secret_id
          AUTH_GITHUB_SECRET = google_secret_manager_secret.github_oauth["auth-github-secret"].secret_id
        }
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value
              version = "latest"
            }
          }
        }
      }
      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image, client, client_version]
  }

  depends_on = [google_secret_manager_secret_iam_member.readers, google_secret_manager_secret_version.placeholder]
}

resource "google_cloud_run_v2_service_iam_member" "public" {
  for_each = var.public_access ? {
    api = google_cloud_run_v2_service.api.name
    web = google_cloud_run_v2_service.web.name
  } : {}
  name     = each.value
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ---------------------------------------------------------------- Jobs: poller and migrations

resource "google_cloud_run_v2_job" "poller" {
  name                = "${local.name}-github-poller"
  location            = var.region
  deletion_protection = false

  template {
    task_count = 1
    template {
      service_account = google_service_account.sa["poller"].email
      timeout         = "1800s"
      max_retries     = 1 # exit 1 = a stream failed (collectors/github_poller/__main__.py)

      containers {
        name    = "poller"
        image   = local.app_image
        command = ["python", "-m", "collectors.github_poller"]
        args    = ["--release", var.poll_release]

        dynamic "env" {
          for_each = merge(local.common_env, { OTEL_SERVICE_NAME = "tpm-github-poller" })
          content {
            name  = env.key
            value = env.value
          }
        }
        env {
          name = "DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.database_url.secret_id
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

        volume_mounts {
          name       = "cloudsql"
          mount_path = "/cloudsql"
        }
      }

      containers {
        name  = "otel-collector"
        image = local.otel_image
        args  = ["--config=/etc/otelcol/config.yaml"]
        volume_mounts {
          name       = "otel-config"
          mount_path = "/etc/otelcol"
        }
      }

      volumes {
        name = "cloudsql"
        cloud_sql_instance {
          instances = [google_sql_database_instance.db.connection_name]
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
  }

  depends_on = [
    google_secret_manager_secret_iam_member.readers,
    google_secret_manager_secret_version.otel_config,
    google_secret_manager_secret_version.placeholder,
    # Cloud Run refuses a secret with no version; this one waits for Cloud SQL.
    google_secret_manager_secret_version.database_url,
  ]

  # The deploy workflow rolls out new images; Terraform owns everything else.
  lifecycle {
    ignore_changes = [template[0].template[0].containers[0].image, client, client_version]
  }
}

# Run before each deploy: gcloud run jobs execute tpm-migrate --wait
resource "google_cloud_run_v2_job" "migrate" {
  name                = "${local.name}-migrate"
  location            = var.region
  deletion_protection = false

  template {
    task_count = 1
    template {
      service_account = google_service_account.sa["migrate"].email
      timeout         = "600s"
      max_retries     = 0

      containers {
        image   = local.app_image
        command = ["alembic", "upgrade", "head"]
        env {
          name = "DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.database_url.secret_id
              version = "latest"
            }
          }
        }
        volume_mounts {
          name       = "cloudsql"
          mount_path = "/cloudsql"
        }
      }

      volumes {
        name = "cloudsql"
        cloud_sql_instance {
          instances = [google_sql_database_instance.db.connection_name]
        }
      }
    }
  }

  depends_on = [
    google_secret_manager_secret_iam_member.readers,
    google_secret_manager_secret_version.database_url,
  ]

  # The deploy workflow rolls out new images; Terraform owns everything else.
  lifecycle {
    ignore_changes = [template[0].template[0].containers[0].image, client, client_version]
  }
}
