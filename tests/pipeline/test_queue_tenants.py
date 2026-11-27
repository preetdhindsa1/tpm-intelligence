"""Each queued event carries its tenant; the worker stores it for that tenant (ADR-0034)."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from pipeline.events import NormalizedEvent
from pipeline.memory import InMemoryTransport
from pipeline.queue import EVENTS_TOPIC, EventConsumer, EventPublisher
from pipeline.sample import k8s_6395_tracked_no
from pipeline.store.tenancy import current_tenant, use_tenant

SUB = "test"


class Recorder:
    """A batch store that records which tenant each batch was stored for."""

    def __init__(self, fail_for: str | None = None) -> None:
        self.batches: list[tuple[str | None, int]] = []
        self.fail_for = fail_for

    def store(self, events: Sequence[NormalizedEvent]) -> set[str]:
        if current_tenant.get() == self.fail_for:
            raise RuntimeError("database hiccup")
        self.batches.append((current_tenant.get(), len(events)))
        return {e.event_id for e in events}

    def announce(self, event: NormalizedEvent) -> None:
        pass


def _publish(transport: InMemoryTransport, tenant: str, n: int = 1) -> None:
    with use_tenant(tenant):
        for _ in range(n):
            EventPublisher(transport).publish(k8s_6395_tracked_no())


def test_the_tenant_travels_with_the_message() -> None:
    transport = InMemoryTransport()
    _publish(transport, "acme")
    (message,) = transport.pull(EVENTS_TOPIC, SUB, 10, 0)
    assert message.attributes["tenant_id"] == "acme"


def test_publishing_with_no_tenant_is_refused() -> None:
    token = current_tenant.set(None)
    try:
        with pytest.raises(RuntimeError, match="no tenant"):
            EventPublisher(InMemoryTransport()).publish(k8s_6395_tracked_no())
    finally:
        current_tenant.reset(token)


def test_a_mixed_batch_is_stored_per_tenant() -> None:
    transport, store = InMemoryTransport(), Recorder()
    _publish(transport, "acme", 2)
    _publish(transport, "demo", 1)
    _publish(transport, "acme", 1)
    seen: list[str | None] = []
    consumer = EventConsumer(transport, SUB, handler=lambda e: seen.append(None), batch=store)
    with use_tenant("globex"):  # the worker's own tenant must not decide where events go
        assert consumer.poll_once() == 4
    assert sorted(store.batches) == [("acme", 3), ("demo", 1)]


def test_one_message_at_a_time_uses_the_messages_tenant() -> None:
    transport = InMemoryTransport()
    _publish(transport, "acme")
    seen: list[str | None] = []
    consumer = EventConsumer(transport, SUB, handler=lambda e: seen.append(current_tenant.get()))
    assert consumer.poll_once() == 1
    assert seen == ["acme"]


def test_a_message_from_before_tenants_is_the_demos() -> None:
    transport = InMemoryTransport()
    transport.publish(EVENTS_TOPIC, k8s_6395_tracked_no().to_bytes(), {"event_type": "x"})
    seen: list[str | None] = []
    consumer = EventConsumer(transport, SUB, handler=lambda e: seen.append(current_tenant.get()))
    consumer.poll_once()
    assert seen == ["demo"]


def test_a_failed_tenant_group_falls_back_without_losing_the_others() -> None:
    transport, store = InMemoryTransport(), Recorder(fail_for="acme")
    _publish(transport, "acme", 2)
    _publish(transport, "demo", 2)
    seen: list[str | None] = []
    consumer = EventConsumer(transport, SUB, handler=lambda e: seen.append(current_tenant.get()),
                             batch=store)  # fmt: skip
    assert consumer.poll_once() == 4
    assert store.batches == [("demo", 2)]
    assert seen == ["acme", "acme"]  # acme's events went one at a time, for acme
