"""Only AI spans go to Langfuse."""

from __future__ import annotations

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from observability.langfuse_export import langfuse_processor


def test_only_ai_spans_are_forwarded(monkeypatch: object) -> None:
    exporter = InMemorySpanExporter()
    processor = langfuse_processor(exporter)
    assert processor is not None
    provider = TracerProvider()
    provider.add_span_processor(processor)
    tracer = provider.get_tracer("t")
    with tracer.start_as_current_span("ai.vp_summary"):
        pass
    with tracer.start_as_current_span("chat claude", attributes={"gen_ai.operation.name": "chat"}):
        pass
    with tracer.start_as_current_span("GET /releases"):
        pass
    provider.force_flush()
    assert sorted(s.name for s in exporter.get_finished_spans()) == ["ai.vp_summary", "chat claude"]


def test_disabled_without_configuration(monkeypatch: object) -> None:
    for var in ("LANGFUSE_HOST", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        monkeypatch.delenv(var, raising=False)  # type: ignore[attr-defined]
    assert langfuse_processor() is None
