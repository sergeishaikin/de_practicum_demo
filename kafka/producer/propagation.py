"""W3C trace-context propagation through confluent-kafka headers."""

from __future__ import annotations

from typing import Iterable

try:
    from opentelemetry.propagators.textmap import Getter, Setter
    from opentelemetry.trace.propagation.tracecontext import (
        TraceContextTextMapPropagator,
    )
except ImportError:  # pragma: no cover - dependency is present in the image
    Getter = object  # type: ignore[misc,assignment]
    Setter = object  # type: ignore[misc,assignment]
    TraceContextTextMapPropagator = None  # type: ignore[assignment,misc]


class _Setter:
    def set(self, carrier: dict[str, str], key: str, value: str) -> None:
        carrier[key] = value


class _Getter:
    def get(self, carrier: dict[str, str], key: str) -> list[str]:
        value = carrier.get(key)
        return [] if value is None else [value]

    def keys(self, carrier: dict[str, str]) -> list[str]:
        return list(carrier)


_PROPAGATOR = TraceContextTextMapPropagator() if TraceContextTextMapPropagator else None
_SETTER = _Setter()
_GETTER = _Getter()


def inject_headers(
    headers: Iterable[tuple[str, bytes | str]] | None = None,
) -> list[tuple[str, bytes]]:
    """Return existing headers plus one W3C ``traceparent`` value."""

    result = [
        (key, value.encode() if isinstance(value, str) else value)
        for key, value in (headers or ())
    ]
    carrier: dict[str, str] = {}
    if _PROPAGATOR is not None:
        _PROPAGATOR.inject(carrier, setter=_SETTER)
    for key, value in carrier.items():
        result = [
            (existing_key, existing_value)
            for existing_key, existing_value in result
            if existing_key != key
        ]
        result.append((key, value.encode("ascii")))
    return result


def extract_context(headers: Iterable[tuple[str, bytes | str]] | None):
    """Extract a context, tolerating missing, invalid or duplicate headers."""

    carrier: dict[str, str] = {}
    for key, value in headers or ():
        if key not in carrier:
            carrier[key] = (
                value.decode("ascii", errors="ignore")
                if isinstance(value, bytes)
                else value
            )
    if _PROPAGATOR is None:
        return None
    return _PROPAGATOR.extract(carrier, getter=_GETTER)
