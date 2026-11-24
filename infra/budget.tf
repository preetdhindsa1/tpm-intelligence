# Cost alert (roadmap hardening; owner chose $150/month on 2026-11-24). The estimate was
# about $95-125 a month, plus the always-warm webhook instance (#36's PR notes). Emails go to
# the same channel as the other alerts (#14).
data "google_project" "this" {
  project_id = var.project_id
}

resource "google_billing_budget" "monthly" {
  provider        = google.billing
  count           = var.billing_account == "" ? 0 : 1
  billing_account = var.billing_account
  display_name    = "TPM: monthly cost (${var.monthly_budget_usd} USD)"

  budget_filter {
    projects = ["projects/${data.google_project.this.number}"]
  }

  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(var.monthly_budget_usd)
    }
  }

  threshold_rules {
    threshold_percent = 0.5
  }
  threshold_rules {
    threshold_percent = 0.9
  }
  threshold_rules {
    threshold_percent = 1.0
  }
  threshold_rules {
    threshold_percent = 1.0
    spend_basis       = "FORECASTED_SPEND"
  }

  all_updates_rule {
    monitoring_notification_channels = local.alert_channels
    disable_default_iam_recipients   = false # billing admins keep the default emails too
  }

  depends_on = [google_project_service.apis]
}
