"""Fail-open tracing for the durable metrics projection service."""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Iterator

LOGGER = logging.getLogger(__name__)


class Telemetry:
    def __init__(self, service_name: str) -> None:
        self.provider: Any = None
        self.logger_provider: Any = None
        self.logger: Any = None
        self.tracer: Any = _NoopTracer()
        if os.getenv("OTEL_ENABLED", "0") != "1":
            return
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )
            from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (  # type: ignore[import-not-found]
                OTLPLogExporter,
            )
            from opentelemetry.sdk._logs import LoggerProvider  # type: ignore[import-not-found]
            from opentelemetry.sdk._logs.export import (  # type: ignore[import-not-found]
                BatchLogRecordProcessor,
            )
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            endpoint = os.getenv(
                "OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317"
            )
            provider = TracerProvider(
                resource=Resource.create(
                    {
                        "service.name": service_name,
                        "service.namespace": os.getenv(
                            "OTEL_SERVICE_NAMESPACE", "de-practicum"
                        ),
                        "deployment.environment.name": os.getenv(
                            "OTEL_DEPLOYMENT_ENVIRONMENT", "local"
                        ),
                    }
                )
            )
            provider.add_span_processor(
                BatchSpanProcessor(
                    OTLPSpanExporter(
                        endpoint=endpoint,
                        insecure=endpoint.startswith("http://"),
                        timeout=float(os.getenv("OTEL_EXPORTER_OTLP_TIMEOUT", "5")),
                    ),
                    max_queue_size=int(os.getenv("OTEL_QUEUE_SIZE", "2048")),
                    max_export_batch_size=int(os.getenv("OTEL_BATCH_SIZE", "128")),
                )
            )
            self.provider = provider
            self.tracer = provider.get_tracer("de-practicum")
            logger_provider = LoggerProvider(resource=provider.resource)
            logger_provider.add_log_record_processor(
                BatchLogRecordProcessor(
                    OTLPLogExporter(
                        endpoint=endpoint,
                        insecure=endpoint.startswith("http://"),
                        timeout=float(os.getenv("OTEL_EXPORTER_OTLP_TIMEOUT", "5")),
                    )
                )
            )
            self.logger_provider = logger_provider
            self.logger = logger_provider.get_logger("de-practicum")
        except Exception:  # pragma: no cover - image smoke path
            LOGGER.exception("OpenTelemetry setup failed; continuing fail-open")

    @contextmanager
    def span(self, name: str) -> Iterator[Any]:
        try:
            span_context = self.tracer.start_as_current_span(name)
        except Exception:  # pragma: no cover
            LOGGER.exception("OpenTelemetry span failed; continuing fail-open")
            yield _NoopSpan()
            return
        with span_context as span:
            yield span

    def shutdown(self) -> None:
        if self.provider is not None:
            try:
                self.provider.shutdown()
            except Exception:  # pragma: no cover
                LOGGER.exception("OpenTelemetry shutdown failed; continuing")
        if self.logger_provider is not None:
            try:
                self.logger_provider.shutdown()
            except Exception:  # pragma: no cover
                LOGGER.exception("OpenTelemetry log shutdown failed; continuing")

    def log(self, body: str) -> None:
        try:
            if self.logger is not None:
                self.logger.emit(body=body)
        except Exception:  # pragma: no cover
            LOGGER.exception("OpenTelemetry log failed; continuing fail-open")


class _NoopTracer:
    @contextmanager
    def start_as_current_span(self, _name: str) -> Iterator[Any]:
        yield _NoopSpan()


class _NoopSpan:
    def set_attribute(self, _key: str, _value: Any) -> None:
        return None


def setup_telemetry(service_name: str) -> Telemetry:
    return Telemetry(service_name)
