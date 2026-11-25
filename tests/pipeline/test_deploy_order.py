"""Deploy readers before writers: the worker must understand new event fields first (#117)."""

from __future__ import annotations

from pathlib import Path

DEPLOY = Path(__file__).parents[2] / ".github" / "workflows" / "deploy.yml"


def test_the_api_worker_is_updated_before_any_collector() -> None:
    text = DEPLOY.read_text()
    api = text.index("gcloud run services update tpm-api")
    for writer in ("tpm-github-poller", "tpm-jira-collector", "services update tpm-webhooks"):
        assert api < text.index(writer), f"{writer} is updated before tpm-api"
    assert text.index("jobs execute tpm-migrate") < api  # the schema still migrates first
