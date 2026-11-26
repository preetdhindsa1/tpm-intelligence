"""Shared fixtures."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

# OTel allows the global tracer provider to be set once per process, so install a
# single in-memory exporter for the whole test session.
_EXPORTER = InMemorySpanExporter()
_provider = TracerProvider()
_provider.add_span_processor(SimpleSpanProcessor(_EXPORTER))
trace.set_tracer_provider(_provider)


@pytest.fixture
def spans() -> Iterator[InMemorySpanExporter]:
    """Finished spans recorded during one test (cleared before and after)."""
    _EXPORTER.clear()
    yield _EXPORTER
    _EXPORTER.clear()


@pytest.fixture(autouse=True)
def demo_tenant() -> Iterator[None]:
    """Tests run for the public demo tenant, as the jobs and the API do by default
    (ADR-0034). Tests of the no-tenant case reset it themselves."""
    from pipeline.store.tenancy import DEMO, use_tenant

    with use_tenant(DEMO):
        yield
