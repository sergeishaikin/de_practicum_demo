"""Fail-open OpenTelemetry setup for first-party Python services.

Telemetry is opt-in (``OTEL_ENABLED=1``).  The module deliberately keeps the
existing Prometheus/PostgreSQL metrics path independent: exporter setup errors
produce a no-op provider and never reach the data path.
"""

from __future__ import annotations

import logging
import os
import re
from contextlib import contextmanager
from typing import Any, Iterator

LOGGER = logging.getLogger(__name__)

OTEL_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
OTEL_TIMEOUT = float(os.getenv("OTEL_EXPORTER_OTLP_TIMEOUT", "5"))
OTEL_NAMESPACE = os.getenv("OTEL_SERVICE_NAMESPACE", "de-practicum")
OTEL_ENVIRONMENT = os.getenv("OTEL_DEPLOYMENT_ENVIRONMENT", "local")

_DENIED_KEYS = re.compile(
    r"(?i)(password|secret|authorization|token|api[_-]?key|connection|string|"
    r"customer[_-]?email|email|pii|payload)"
)
_DENIED_VALUES = (
    re.compile(r"(?i)bearer\s+[a-z0-9._~-]+"),
    re.compile(r"(?i)select\s+customer_email\s+from\s+orders"),
    re.compile(r"(?i)customer[._-]?email\s*[:=]\s*[^\s,;]+"),
    re.compile(r"(?i)[^\s,;]+@[^\s,;]+\.[a-z]{2,}"),
    re.compile(r"(?i)full[-_ ]?payload[-_ ]?marker"),
    re.compile(r"(?i)do[-_ ]?not[-_ ]?store"),
)


def _safe_value(value: Any) -> Any:
    text = str(value)
    for pattern in _DENIED_VALUES:
        text = pattern.sub("[REDACTED]", text)
    return text


def _safe_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    return {
        key: "[REDACTED]" if _DENIED_KEYS.search(key) else _safe_value(value)
        for key, value in attributes.items()
    }


class Telemetry:
    """Small wrapper that makes setup and shutdown safe and testable."""

    def __init__(self, service_name: str) -> None:
        self.service_name = service_name
        self._tracer_provider: Any = None
        self._logger_provider: Any = None
        self.enabled = False
        self.tracer: Any = _NoopTracer()
        self.logger: Any = logging.getLogger(service_name)
        if os.getenv("OTEL_ENABLED", "0") != "1":
            return
        self._setup()

    def _setup(self) -> None:
        try:
            from opentelemetry import trace  # type: ignore[import-not-found]
            from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (  # type: ignore[import-not-found]
                OTLPLogExporter,
            )
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (  # type: ignore[import-not-found]
                OTLPSpanExporter,
            )
            from opentelemetry.sdk._logs import LoggerProvider  # type: ignore[import-not-found]
            from opentelemetry.sdk._logs.export import (  # type: ignore[import-not-found]
                BatchLogRecordProcessor,
            )
            from opentelemetry.sdk.resources import Resource  # type: ignore[import-not-found]
            from opentelemetry.sdk.trace import TracerProvider  # type: ignore[import-not-found]
            from opentelemetry.sdk.trace.export import (  # type: ignore[import-not-found]
                BatchSpanProcessor,
            )

            resource = Resource.create(
                {
                    "service.name": self.service_name,
                    "service.namespace": OTEL_NAMESPACE,
                    "deployment.environment.name": OTEL_ENVIRONMENT,
                }
            )
            tracer_provider = TracerProvider(resource=resource)
            tracer_provider.add_span_processor(
                BatchSpanProcessor(
                    OTLPSpanExporter(
                        endpoint=OTEL_ENDPOINT,
                        insecure=OTEL_ENDPOINT.startswith("http://"),
                        timeout=OTEL_TIMEOUT,
                    ),
                    max_queue_size=int(os.getenv("OTEL_QUEUE_SIZE", "2048")),
                    max_export_batch_size=int(os.getenv("OTEL_BATCH_SIZE", "128")),
                    schedule_delay_millis=int(os.getenv("OTEL_BATCH_DELAY_MS", "1000")),
                )
            )
            logger_provider = LoggerProvider(resource=resource)
            logger_provider.add_log_record_processor(
                BatchLogRecordProcessor(
                    OTLPLogExporter(
                        endpoint=OTEL_ENDPOINT,
                        insecure=OTEL_ENDPOINT.startswith("http://"),
                        timeout=OTEL_TIMEOUT,
                    ),
                    max_queue_size=int(os.getenv("OTEL_QUEUE_SIZE", "2048")),
                    max_export_batch_size=int(os.getenv("OTEL_BATCH_SIZE", "128")),
                    schedule_delay_millis=int(os.getenv("OTEL_BATCH_DELAY_MS", "1000")),
                )
            )
            self._tracer_provider = tracer_provider
            self._logger_provider = logger_provider
            self.tracer = tracer_provider.get_tracer("de-practicum")
            self.logger = logger_provider.get_logger("de-practicum")
            trace.set_tracer_provider(tracer_provider)
            self.enabled = True
        except Exception:  # pragma: no cover - exercised in image smoke tests
            LOGGER.exception("OpenTelemetry setup failed; continuing fail-open")

    @contextmanager
    def span(
        self, name: str, attributes: dict[str, Any] | None = None
    ) -> Iterator[Any]:
        """Create a span, or a no-op context, without affecting business work."""

        try:
            span_context = self.tracer.start_as_current_span(
                name, attributes=attributes
            )
        except Exception:  # pragma: no cover - exporter/runtime defensive boundary
            LOGGER.exception("OpenTelemetry span failed; continuing fail-open")
            yield _NoopSpan()
            return
        with span_context as span:
            yield span

    def shutdown(self) -> None:
        for provider in (self._logger_provider, self._tracer_provider):
            if provider is not None:
                try:
                    provider.shutdown()
                except Exception:  # pragma: no cover - defensive shutdown path
                    LOGGER.exception("OpenTelemetry shutdown failed; continuing")

    def log(
        self,
        body: str,
        *,
        event_name: str,
        severity: str = "INFO",
        attributes: dict[str, Any] | None = None,
    ) -> None:
        """Emit one bounded structured record while preserving fail-open semantics.

        ``event_name`` and ``severity`` are required at the call boundary so
        first-party records cannot silently fall back to prose-only logs.
        Resource attributes provide service identity and the SDK supplies the
        timestamp; event metadata is attached as structured attributes.
        """
        if not self.enabled:
            return
        try:
            safe_attributes = _safe_attributes(attributes or {})
            safe_attributes.setdefault("event.name", _safe_value(event_name))
            safe_attributes.setdefault("severity", _safe_value(severity.upper()))
            try:
                from opentelemetry import trace

                context = trace.get_current_span().get_span_context()
                if context.is_valid:
                    safe_attributes.setdefault("trace_id", f"{context.trace_id:032x}")
                    safe_attributes.setdefault("span_id", f"{context.span_id:016x}")
            except Exception:  # pragma: no cover - optional SDK boundary
                pass
            self.logger.emit(body=_safe_value(body), attributes=safe_attributes)
        except Exception:  # pragma: no cover - exporter/runtime boundary
            LOGGER.exception("OpenTelemetry log failed; continuing fail-open")


class _NoopTracer:
    @contextmanager
    def start_as_current_span(
        self, _name: str, attributes: dict[str, Any] | None = None
    ) -> Iterator[Any]:
        del attributes
        yield _NoopSpan()


class _NoopSpan:
    def set_attribute(self, _key: str, _value: Any) -> None:
        return None

    def record_exception(self, _exception: BaseException) -> None:
        return None

    def set_status(self, _status: Any) -> None:
        return None


def setup_telemetry(service_name: str) -> Telemetry:
    return Telemetry(service_name)


def current_trace_exemplar() -> dict[str, str] | None:
    """Return a sampled current trace id for a bounded metric exemplar.

    Exemplars are optional correlation metadata, not metric dimensions.  The
    import and lookup are deliberately fail-open because the root environment
    and the telemetry-disabled profile do not install/use the OTel SDK.
    """

    if os.getenv("OTEL_ENABLED", "0") != "1":
        return None
    try:
        from opentelemetry import trace

        context = trace.get_current_span().get_span_context()
        if not context.is_valid or not context.trace_flags.sampled:
            return None
        return {"trace_id": f"{context.trace_id:032x}"}
    except Exception:  # pragma: no cover - optional SDK/runtime boundary
        LOGGER.debug("Unable to read OTel context for metric exemplar", exc_info=True)
        return None
