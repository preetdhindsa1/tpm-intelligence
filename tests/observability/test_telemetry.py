"""Telemetry wiring: providers carry the service name; logs are JSON with trace IDs."""

from __future__ import annotations

import io
import json
import logging

import pytest
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from observability.json_logging import JsonFormatter
from observability.telemetry import build_providers


def _capture_logger(name: str) -> tuple[logging.Logger, io.StringIO]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter("test-service"))
    logger = logging.getLogger(name)
    logger.handlers[:] = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    return logger, stream


def test_log_line_carries_active_trace_and_span_ids() -> None:
    exporter = InMemorySpanExporter()
    telemetry = build_providers("test-service", span_exporters=[exporter], metric_readers=[])
    tracer = telemetry.tracer_provider.get_tracer(__name__)
    logger, stream = _capture_logger("test.trace_ids")

    with tracer.start_as_current_span("unit-of-work") as span:
        logger.info("inside span", extra={"release": "v1.38"})
        ctx = span.get_span_context()

    record = json.loads(stream.getvalue())
    assert record["message"] == "inside span"
    assert record["service"] == "test-service"
    assert record["severity"] == "INFO"
    assert record["release"] == "v1.38"
    assert record["trace_id"] == format(ctx.trace_id, "032x")
    assert record["span_id"] == format(ctx.span_id, "016x")
    telemetry.shutdown()
    assert [s.name for s in exporter.get_finished_spans()] == ["unit-of-work"]


def test_log_line_outside_span_has_no_trace_id() -> None:
    logger, stream = _capture_logger("test.no_span")
    logger.warning("no span here")
    record = json.loads(stream.getvalue())
    assert "trace_id" not in record
    assert record["severity"] == "WARNING"


def test_exceptions_are_serialised_on_one_line() -> None:
    logger, stream = _capture_logger("test.exc")
    try:
        raise ValueError("boom")
    except ValueError:
        logger.exception("failed")
    lines = stream.getvalue().strip().splitlines()
    assert len(lines) == 1
    assert "ValueError: boom" in json.loads(lines[0])["exception"]


def test_resource_names_the_service() -> None:
    telemetry = build_providers("tpm-api", span_exporters=[], metric_readers=[])
    attrs = telemetry.tracer_provider.resource.attributes
    assert attrs["service.name"] == "tpm-api"
    assert attrs["deployment.environment"] == "local"
    telemetry.shutdown()


def test_metrics_are_recorded() -> None:
    reader = InMemoryMetricReader()
    telemetry = build_providers("test-service", span_exporters=[], metric_readers=[reader])
    counter = telemetry.meter_provider.get_meter(__name__).create_counter("things")
    counter.add(3)
    data = reader.get_metrics_data()
    assert data is not None
    points = [
        point.value
        for rm in data.resource_metrics
        for sm in rm.scope_metrics
        for metric in sm.metrics
        if metric.name == "things"
        for point in metric.data.data_points  # type: ignore[union-attr]
    ]
    assert points == [3]
    telemetry.shutdown()


def test_no_otlp_exporter_without_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    telemetry = build_providers("test-service")
    # Only the SDK's no-op multi-processor: nothing registered.
    assert telemetry.tracer_provider._active_span_processor._span_processors == ()
    telemetry.shutdown()
