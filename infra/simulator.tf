# Simulator calibration (ADR-0012, #149): fits the Shadow-Org Simulator for one release from
# the finished releases of the same project and stores it for the API. On demand only:
# a new calibration changes the simulator's numbers, so it is run deliberately, e.g.
#   gcloud run jobs execute tpm-sim-calibrate --region us-central1 --wait
#   gcloud run jobs execute tpm-sim-calibrate --region us-central1 --args=--release,v1.39 --wait
# No AI; reads events and writes one row to sim_calibrations.

variable "sim_calibrate_release" {
  description = "Release the calibration job fits by default: v1.38 (Kubernetes) or <PROJECT>:<release>."
  type        = string
  default     = "KAFKA:4.5.0"
}

resource "google_cloud_run_v2_job" "sim_calibrate" {
  name                = "${local.name}-sim-calibrate"
  location            = var.region
  deletion_protection = false

  template {
    task_count = 1
    template {
      service_account = google_service_account.sa["poller"].email # DB access, nothing else
      timeout         = "1800s"
      max_retries     = 0

      containers {
        name    = "calibrate"
        image   = local.app_image
        command = ["python", "scripts/calibrate_simulator.py"]
        args    = ["--release", var.sim_calibrate_release]

        resources {
          limits = {
            cpu    = "2000m"
            memory = "4Gi" # loads one project's whole event history (Kafka: thousands of PRs)
          }
        }

        dynamic "env" {
          for_each = merge(local.common_env, {
            OTEL_SERVICE_NAME           = "tpm-sim-calibrate"
            OTEL_EXPORTER_OTLP_ENDPOINT = ""
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
