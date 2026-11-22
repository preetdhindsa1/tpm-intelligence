# Event queue (ADR-0001). Names match pipeline/queue.py (EVENTS_TOPIC) and
# pipeline/worker.py (SUBSCRIPTION), run inside the API in the cloud (ADR-0017).

locals {
  pubsub_agent = "serviceAccount:service-${var.project_number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

resource "google_pubsub_topic" "events" {
  name                       = "normalized-events"
  message_retention_duration = "604800s" # 7 days: replay after an outage
  depends_on                 = [google_project_service.apis]
}

resource "google_pubsub_topic" "events_dead_letter" {
  name                       = "normalized-events-dead-letter"
  message_retention_duration = "604800s"
  depends_on                 = [google_project_service.apis]
}

resource "google_pubsub_subscription" "worker" {
  name                       = "worker"
  topic                      = google_pubsub_topic.events.id
  ack_deadline_seconds       = 60
  message_retention_duration = "604800s"

  # Required: Pub/Sub only fills delivery_attempt when a dead-letter policy is set
  # (pipeline/pubsub.py). 5 matches DEFAULT_MAX_DELIVERY_ATTEMPTS.
  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.events_dead_letter.id
    max_delivery_attempts = 5
  }

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }
}

# Kept so dead-lettered messages can be inspected and replayed.
resource "google_pubsub_subscription" "dead_letter_inspect" {
  name                       = "normalized-events-dead-letter-inspect"
  topic                      = google_pubsub_topic.events_dead_letter.id
  message_retention_duration = "604800s"
}

resource "google_pubsub_topic_iam_member" "poller_publishes" {
  topic  = google_pubsub_topic.events.id
  role   = "roles/pubsub.publisher"
  member = google_service_account.sa["poller"].member
}

resource "google_pubsub_subscription_iam_member" "worker_consumes" {
  subscription = google_pubsub_subscription.worker.id
  role         = "roles/pubsub.subscriber"
  member       = google_service_account.sa["api"].member
}

# The worker also dead-letters itself after max attempts (same as the Redis backend).
resource "google_pubsub_topic_iam_member" "worker_dead_letters" {
  topic  = google_pubsub_topic.events_dead_letter.id
  role   = "roles/pubsub.publisher"
  member = google_service_account.sa["api"].member
}

# Pub/Sub's own dead-letter forwarding needs these on its service agent.
resource "google_pubsub_topic_iam_member" "agent_dead_letters" {
  topic  = google_pubsub_topic.events_dead_letter.id
  role   = "roles/pubsub.publisher"
  member = local.pubsub_agent
}

resource "google_pubsub_subscription_iam_member" "agent_acks" {
  subscription = google_pubsub_subscription.worker.id
  role         = "roles/pubsub.subscriber"
  member       = local.pubsub_agent
}
