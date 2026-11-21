"""Pick the queue backend from configuration (``QUEUE_BACKEND``)."""

from __future__ import annotations

import os

from pipeline.queue import Transport


def create_transport() -> Transport:
    """Build the configured transport.

    * ``QUEUE_BACKEND=redis`` (default): uses ``REDIS_URL``.
    * ``QUEUE_BACKEND=pubsub``: uses ``PUBSUB_PROJECT_ID`` (honours ``PUBSUB_EMULATOR_HOST``).
    """
    backend = os.getenv("QUEUE_BACKEND", "redis").lower()
    if backend == "redis":
        from pipeline.redis_streams import RedisStreamsTransport

        return RedisStreamsTransport.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    if backend == "pubsub":
        from pipeline.pubsub import PubSubTransport

        project = os.getenv("PUBSUB_PROJECT_ID")
        if not project:
            raise RuntimeError("QUEUE_BACKEND=pubsub requires PUBSUB_PROJECT_ID")
        return PubSubTransport(project)
    raise RuntimeError(f"unknown QUEUE_BACKEND {backend!r}; expected 'redis' or 'pubsub'")
