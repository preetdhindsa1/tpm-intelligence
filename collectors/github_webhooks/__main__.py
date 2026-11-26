"""Run the webhook receiver (ADR-0020): ``python -m collectors.github_webhooks``.

Environment: ``GITHUB_WEBHOOK_SECRET`` (required; Secret Manager in the cloud),
``GITHUB_TOKEN`` (read-only; used to fetch a planning issue's timeline), the queue
settings (``QUEUE_BACKEND``, ...) and ``PORT``. Accepted repositories come from
``connectors/teams/``.
"""

from __future__ import annotations

import functools
import logging
import os
import sys

SERVICE_NAME = "tpm-webhooks"


def main() -> int:
    """Wire dependencies and serve."""
    from observability.telemetry import init_telemetry

    telemetry = init_telemetry(SERVICE_NAME)
    logger = logging.getLogger("collectors.github_webhooks")
    try:
        import uvicorn
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        from collectors.github_poller.client import GitHubClient
        from collectors.github_poller.sync import fetch_issue_timeline
        from collectors.github_webhooks.app import create_app
        from collectors.github_webhooks.normalize import WebhookNormalizer
        from connectors.load import load_teams
        from pipeline.env import configured
        from pipeline.factory import create_transport
        from pipeline.queue import EventPublisher

        secret = configured("GITHUB_WEBHOOK_SECRET")
        if not secret:
            logger.error("GITHUB_WEBHOOK_SECRET is not set (or still the placeholder)")
            return 2
        token = configured("GITHUB_TOKEN")
        timeline = (
            functools.partial(fetch_issue_timeline, GitHubClient.from_token(token))
            if token
            else None
        )
        normalizer = WebhookNormalizer(load_teams().values(), timeline=timeline)
        publisher = EventPublisher(create_transport())
        app = create_app(
            secret=secret,
            publish=publisher.publish,
            normalize=normalizer,
            allowed_repos=normalizer.repos,
            flush=telemetry.force_flush,
        )
        FastAPIInstrumentor.instrument_app(app, excluded_urls="health")
        uvicorn.run(
            app,
            host="0.0.0.0",  # noqa: S104 - Cloud Run serves on all interfaces
            port=int(os.getenv("PORT", "8080")),
            log_config=None,
        )
        return 0
    finally:
        telemetry.shutdown()


if __name__ == "__main__":
    from pipeline.store.tenancy import cli_tenant, use_tenant

    with use_tenant(cli_tenant()):  # TPM_TENANT, else the public demo (ADR-0034)
        sys.exit(main())
