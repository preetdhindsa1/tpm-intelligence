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

variable "extra_poll_teams" {
  description = "More teams the poller syncs in the same run, as team id => release (connectors/teams/<id>.yaml). Polled after Kubernetes, in key order."
  type        = map(string)
  default     = { "tpm-intelligence" = "Phase 3", "kafka" = "4.5.0" }
}

variable "jira_releases" {
  description = "Kafka fix versions the hourly Jira collector syncs (#47): the current release and the finished one it calibrates on. Without the finished one, its freeze dates never reach the engine and the current release has no history to forecast from."
  type        = list(string)
  default     = ["4.4.0", "4.5.0"]
}

variable "jira_schedule" {
  description = "Cron for the Jira collector. Hourly: Apache rate-limits automated tools (CLAUDE.md section 7)."
  type        = string
  default     = "17 * * * *"
}

variable "poll_schedule" {
  description = "Cron for the GitHub poller. Every 5 minutes keeps data freshness under the 10-minute SLO (CLAUDE.md section 9)."
  type        = string
  default     = "*/5 * * * *"
}

variable "web_service_name" {
  description = "Cloud Run service for the web app; it is also the first part of the public URL (https://<name>-<project number>.<region>.run.app)."
  type        = string
  default     = "program-intelligence-platform" # was tpm-intelligence until 2026-11-23 (ADR-0021)
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

variable "alert_email" {
  description = "Email address that receives alerts. Set it in terraform.tfvars (gitignored), never in code; empty means no email channel."
  type        = string
  default     = ""
  sensitive   = true
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

variable "enable_ai_budget_alert" {
  description = "Create the AI-spend alert. Needs the ai_budget_used_fraction metric to exist (after the first AI call)."
  type        = bool
  default     = false
}

variable "billing_account" {
  description = "Cloud Billing account ID for the budget alert (budget.tf), e.g. 012345-6789AB-CDEF01. Set it in terraform.tfvars; empty means no budget."
  type        = string
  default     = ""
}

variable "monthly_budget_usd" {
  description = "Monthly cost budget in USD; alerts at 50%, 90% and 100% of actual spend and 100% of forecast (owner's choice, 2026-11-24)."
  type        = number
  default     = 150
}
