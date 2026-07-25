"""OpenTelemetry setup: console default, OTLP→Phoenix optional, no-op path."""

from __future__ import annotations

import contextlib
import os
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
    SpanExporter,
)

_PROVIDER: TracerProvider | None = None
SECRET_ENV_KEYS = (
    "OPENROUTER_API_KEY",
    "OPENAI_API_KEY",
    "AWS_SECRET_ACCESS_KEY",
    "GITHUB_TOKEN",
)


def _install_provider(provider: TracerProvider, *, force: bool) -> None:
    """Install ``provider`` as the process-wide TracerProvider.

    OpenTelemetry only allows ``set_tracer_provider`` once. Tests pass
    ``force=True`` to replace the provider (and attach an in-memory exporter).
    """
    if force:
        # Reset the one-shot latch so set_tracer_provider can succeed again.
        once = getattr(trace, "_TRACER_PROVIDER_SET_ONCE", None)
        if once is not None and hasattr(once, "_done"):
            once._done = False
        trace._TRACER_PROVIDER = None  # noqa: SLF001 — test-only provider swap
    trace.set_tracer_provider(provider)


def setup_tracing(
    *,
    service_name: str = "guidance-watch",
    exporter: SpanExporter | None = None,
    force: bool = False,
) -> TracerProvider:
    """Configure global tracer provider.

    Priority:
    1. Explicit ``exporter`` (tests)
    2. OTLP HTTP if ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set (Phoenix)
    3. Console exporter
    4. Set ``GUIDANCE_WATCH_OTEL=off`` for no-op (no processors)
    """
    global _PROVIDER
    if _PROVIDER is not None and not force:
        return _PROVIDER

    if force and _PROVIDER is not None:
        with contextlib.suppress(Exception):
            _PROVIDER.shutdown()

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    mode = (os.environ.get("GUIDANCE_WATCH_OTEL") or "auto").lower()
    if mode == "off" and exporter is None:
        _install_provider(provider, force=force)
        _PROVIDER = provider
        return provider

    if exporter is not None:
        provider.add_span_processor(SimpleSpanProcessor(exporter))
    else:
        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
        if endpoint:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )

            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        elif mode != "off":
            provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

    _install_provider(provider, force=force)
    _PROVIDER = provider
    return provider


def get_tracer(name: str = "guidance_watch") -> trace.Tracer:
    if _PROVIDER is None:
        setup_tracing()
    assert _PROVIDER is not None
    # Prefer our SDK provider so test exporters attached via setup_tracing(force=True)
    # receive spans even if another global provider was installed earlier.
    return _PROVIDER.get_tracer(name)


def redact_value(value: Any) -> Any:
    """Redact strings that look like secrets or match secret env values."""
    if not isinstance(value, str):
        return value
    secret_values = {os.environ[k] for k in SECRET_ENV_KEYS if os.environ.get(k)}
    if value in secret_values and value:
        return "[REDACTED]"
    lower = value.lower()
    if any(token in lower for token in ("api_key", "bearer ", "authorization")):
        return "[REDACTED]"
    return value


def set_attrs(span: trace.Span, attrs: dict[str, Any]) -> None:
    for key, value in attrs.items():
        if value is None:
            continue
        span.set_attribute(key, redact_value(value))
