"""Send AI spans (not the whole trace firehose) to Langfuse over OTLP (ADR-0009).

Enabled when ``LANGFUSE_HOST``, ``LANGFUSE_PUBLIC_KEY`` and ``LANGFUSE_SECRET_KEY`` are set.
Jaeger / Cloud Trace still receive every span through the normal exporter.
"""

from __future__ import annotations

import base64
import os

from opentelemetry.context import Context
from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter

_AI_PREFIXES = ("ai.", "anthropic.")
_GENAI_KEYS = ("gen_ai.operation.name", "gen_ai.system", "gen_ai.provider.name")


def is_ai_span(span: ReadableSpan) -> bool:
    """Our ``ai.*`` spans and the Anthropic SDK's GenAI spans."""
    if span.name.startswith(_AI_PREFIXES):
        return True
    attrs = span.attributes or {}
    return any(k in attrs for k in _GENAI_KEYS)


class AISpanFilter(SpanProcessor):
    """Forward only AI spans to the wrapped processor."""

    def __init__(self, inner: SpanProcessor) -> None:
        self._inner = inner

    def on_start(self, span: Span, parent_context: Context | None = None) -> None:
        """Nothing to do at start; filtering needs the finished span."""

    def on_end(self, span: ReadableSpan) -> None:
        """Forward AI spans."""
        if is_ai_span(span):
            self._inner.on_end(span)

    def shutdown(self) -> None:
        """Flush and stop the inner processor."""
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        """Flush the inner processor."""
        return self._inner.force_flush(timeout_millis)


def langfuse_processor(exporter: SpanExporter | None = None) -> SpanProcessor | None:
    """The filtered Langfuse processor, or None when Langfuse is not configured."""
    host = os.getenv("LANGFUSE_HOST")
    public, secret = os.getenv("LANGFUSE_PUBLIC_KEY"), os.getenv("LANGFUSE_SECRET_KEY")
    if exporter is None:
        if not (host and public and secret):
            return None
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        token = base64.b64encode(f"{public}:{secret}".encode()).decode()
        exporter = OTLPSpanExporter(
            endpoint=f"{host.rstrip('/')}/api/public/otel/v1/traces",
            headers={"Authorization": f"Basic {token}"},
            timeout=30,  # first ingest after start-up can exceed the 10 s default (2026-11-22)
        )
    return AISpanFilter(BatchSpanProcessor(exporter))
