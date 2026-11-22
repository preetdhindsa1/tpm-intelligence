variable "project_id" {
  description = "Google Cloud project ID."
  type        = string
}

variable "project_number" {
  description = "Google Cloud project number (for the Pub/Sub service agent). Passed in so plan needs no API lookup."
  type        = string
}

variable "region" {
  description = "Region for every regional resource."
  type        = string
  default     = "us-central1"
}

variable "image_tag" {
  description = "Tag of the app and web images in Artifact Registry (CI pushes the git SHA)."
  type        = string
  default     = "latest"
}

variable "poll_release" {
  description = "Kubernetes release the poller syncs, e.g. v1.38."
  type        = string
  default     = "v1.38"
}

variable "poll_schedule" {
  description = "Cron for the GitHub poller. Every 5 minutes keeps data freshness under the 10-minute SLO (CLAUDE.md section 9)."
  type        = string
  default     = "*/5 * * * *"
}

variable "cors_origins" {
  description = "Extra browser origins allowed to call the API (e.g. a custom domain). The Cloud Run web URL is always allowed."
  type        = list(string)
  default     = []
}

variable "public_access" {
  description = "Allow unauthenticated access to the web app and API (public demo on public data)."
  type        = bool
  default     = true
}

variable "db_tier" {
  description = "Cloud SQL machine tier."
  type        = string
  default     = "db-g1-small" # shared core, option B (ADR-0017); about 300k events fit easily
}

variable "alert_notification_channels" {
  description = "Cloud Monitoring notification channel IDs for alerts (empty: alerts fire with no notification)."
  type        = list(string)
  default     = []
}

variable "approvers" {
  description = "GitHub logins allowed to approve and act (ADR-0016)."
  type        = list(string)
  default     = []
}

variable "github_repo" {
  description = "owner/name of the repository whose main branch may deploy (keyless, ADR-0017)."
  type        = string
  default     = "preetdhindsa1/tpm-intelligence"
}
