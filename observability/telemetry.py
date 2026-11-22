"""OpenTelemetry setup shared by every service (CLAUDE.md section 9).

Every service calls :func:`init_telemetry` once at startup. It installs:

* a tracer provider (OTLP export when ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set),
* a meter provider (same rule),
* JSON logging on the root logger, with ``trace_id``/``span_id`` on every line.

Exporters follow the standard ``OTEL_*`` environment variables, so the same code
works locally (Collector in Docker Compose) and on Cloud Run.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass

from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import MetricReader, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter

from observability.json_logging import configure_json_logging

_OTLP_ENDPOINT_ENV = "OTEL_EXPORTER_OTLP_ENDPOINT"


@dataclass(frozen=True)
class Telemetry:
    """Handles to the installed providers; call :meth:`shutdown` on exit to flush."""

    tracer_provider: TracerProvider
    meter_provider: MeterProvider

    def shutdown(self) -> None:
        """Flush and stop exporters."""
        self.tracer_provider.shutdown()
        self.meter_provider.shutdown()


def build_resource(service_name: str, service_version: str = "0.1.0") -> Resource:
    """Describe the emitting service; deployment env comes from ``DEPLOY_ENV``."""
    return Resource.create(
        {
            SERVICE_NAME: service_name,
            SERVICE_VERSION: service_version,
            "deployment.environment": os.getenv("DEPLOY_ENV", "local"),
        }
    )


def _default_span_exporters() -> list[SpanExporter]:
    if not os.getenv(_OTLP_ENDPOINT_ENV):
        return []
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

    return [OTLPSpanExporter()]


def _default_metric_readers() -> list[MetricReader]:
    if not os.getenv(_OTLP_ENDPOINT_ENV):
        return []
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

    return [PeriodicExportingMetricReader(OTLPMetricExporter())]


def build_providers(
    service_name: str,
    *,
    span_exporters: Sequence[SpanExporter] | None = None,
    metric_readers: Sequence[MetricReader] | None = None,
) -> Telemetry:
    """Create providers without installing them globally (useful in tests).

    When exporters/readers are not given, OTLP is used if the endpoint env var is
    set; otherwise spans are still created (so logs carry trace IDs) but not exported.
    """
    resource = build_resource(service_name)
    exporters = _default_span_exporters() if span_exporters is None else list(span_exporters)
    readers = _default_metric_readers() if metric_readers is None else list(metric_readers)

    tracer_provider = TracerProvider(resource=resource)
    for exporter in exporters:
        tracer_provider.add_span_processor(BatchSpanProcessor(exporter))
    if span_exporters is None:  # explicit exporters (tests) never leak to Langfuse
        from observability.langfuse_export import langfuse_processor

        langfuse = langfuse_processor()
        if langfuse is not None:
            tracer_provider.add_span_processor(langfuse)
    meter_provider = MeterProvider(resource=resource, metric_readers=readers)
    return Telemetry(tracer_provider=tracer_provider, meter_provider=meter_provider)


def init_telemetry(
    service_name: str,
    *,
    log_level: str | None = None,
    span_exporters: Sequence[SpanExporter] | None = None,
    metric_readers: Sequence[MetricReader] | None = None,
) -> Telemetry:
    """Install global tracing, metrics and JSON logging for ``service_name``.

    Call exactly once per process, before creating tracers, meters or loggers.
    """
    telemetry = build_providers(
        service_name, span_exporters=span_exporters, metric_readers=metric_readers
    )
    trace.set_tracer_provider(telemetry.tracer_provider)
    metrics.set_meter_provider(telemetry.meter_provider)
    configure_json_logging(
        service_name=service_name,
        level=log_level or os.environ.get("LOG_LEVEL") or "INFO",
    )
    logging.getLogger(__name__).info(
        "telemetry initialised",
        extra={"otlp_endpoint": os.getenv(_OTLP_ENDPOINT_ENV) or None},
    )
    return telemetry
