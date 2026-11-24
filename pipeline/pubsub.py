"""Google Cloud Pub/Sub transport (cloud; also works against the Pub/Sub emulator).

Topics and subscriptions are created by Terraform in the cloud. The subscription must
have a dead-letter policy: Pub/Sub only fills ``delivery_attempt`` when one is set.
:meth:`PubSubTransport.dead_letter` also publishes to ``<topic>-dead-letter`` itself, so
behaviour matches the Redis backend whichever path triggers first.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pipeline.queue import ReceivedMessage


def dead_letter_topic(topic: str) -> str:
    """Name of the dead-letter topic for ``topic``."""
    return f"{topic}-dead-letter"


class PubSubTransport:
    """:class:`pipeline.queue.Transport` backed by Google Cloud Pub/Sub (synchronous pull)."""

    system = "gcp_pubsub"

    def __init__(
        self,
        project_id: str,
        *,
        publisher: Any | None = None,
        subscriber: Any | None = None,
        publish_timeout_s: float = 30.0,
        min_pull_timeout_s: float = 20.0,
    ) -> None:
        if publisher is None or subscriber is None:
            from google.cloud import pubsub_v1

            publisher = publisher or pubsub_v1.PublisherClient()
            subscriber = subscriber or pubsub_v1.SubscriberClient()
        self._project = project_id
        self._publisher = publisher
        self._subscriber = subscriber
        self._publish_timeout_s = publish_timeout_s
        self._min_pull_timeout_s = min_pull_timeout_s

    def _topic_path(self, topic: str) -> str:
        return f"projects/{self._project}/topics/{topic}"

    def _subscription_path(self, subscription: str) -> str:
        return f"projects/{self._project}/subscriptions/{subscription}"

    def publish(self, topic: str, data: bytes, attributes: Mapping[str, str]) -> str:
        """Publish and wait for the server-assigned message ID."""
        future = self._publisher.publish(self._topic_path(topic), data, **dict(attributes))
        return str(future.result(timeout=self._publish_timeout_s))

    def pull(
        self, topic: str, subscription: str, max_messages: int, timeout_s: float
    ) -> list[ReceivedMessage]:
        """Synchronous pull; may return fewer messages than requested (or none).

        An empty subscription makes Pub/Sub's pull run out its deadline: that is "no
        messages", not a failure (it used to be logged as a worker crash every few seconds,
        each followed by a 5 s back-off, 2026-11-23).

        The pull waits at least ``min_pull_timeout_s``. With a 2 s client timeout, Pub/Sub
        leased messages to requests the client had already given up on; they stayed hidden
        until the 60 s ack deadline and webhook events reached the page 60-90 s late
        (2026-11-24, #43). A pull still returns as soon as messages exist.
        """
        from google.api_core.exceptions import DeadlineExceeded

        try:
            response = self._subscriber.pull(
                request={
                    "subscription": self._subscription_path(subscription),
                    "max_messages": max_messages,
                },
                timeout=max(timeout_s, self._min_pull_timeout_s),
            )
        except DeadlineExceeded:
            return []
        return [
            ReceivedMessage(
                message_id=received.message.message_id,
                data=bytes(received.message.data),
                attributes=dict(received.message.attributes),
                # 0 means "no dead-letter policy on the subscription"; treat as first attempt.
                delivery_attempt=max(1, int(received.delivery_attempt or 0)),
                ack_id=received.ack_id,
            )
            for received in response.received_messages
        ]

    def ack(self, topic: str, subscription: str, message: ReceivedMessage) -> None:
        """Acknowledge one message."""
        self._subscriber.acknowledge(
            request={
                "subscription": self._subscription_path(subscription),
                "ack_ids": [message.ack_id],
            }
        )

    def ack_many(self, topic: str, subscription: str, messages: list[ReceivedMessage]) -> None:
        """Acknowledge a batch in as few calls as possible (1,000 IDs per request)."""
        ids = [m.ack_id for m in messages]
        for i in range(0, len(ids), 1000):
            self._subscriber.acknowledge(
                request={
                    "subscription": self._subscription_path(subscription),
                    "ack_ids": ids[i : i + 1000],
                }
            )

    def nack(self, topic: str, subscription: str, message: ReceivedMessage) -> None:
        """Set the ack deadline to 0 so Pub/Sub redelivers now."""
        self._subscriber.modify_ack_deadline(
            request={
                "subscription": self._subscription_path(subscription),
                "ack_ids": [message.ack_id],
                "ack_deadline_seconds": 0,
            }
        )

    def dead_letter(self, topic: str, subscription: str, message: ReceivedMessage) -> None:
        """Publish to the dead-letter topic with failure metadata, then ack."""
        attributes = {
            **message.attributes,
            "dead_letter.subscription": subscription,
            "dead_letter.original_id": message.message_id,
            "dead_letter.attempts": str(message.delivery_attempt),
        }
        self.publish(dead_letter_topic(topic), message.data, attributes)
        self.ack(topic, subscription, message)
