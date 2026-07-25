"""Span helpers for filing processing traces."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace

from guidance_watch.telemetry.setup import get_tracer, set_attrs

REQUIRED_SPAN_NAMES = (
    "poll",
    "detect",
    "filter",
    "retrieve metadata",
    "retrieve document",
    "classify",
    "extract guidance",
    "load history",
    "sentiment inference",
    "calculate assessment",
    "render report",
    "persist result",
)


@contextmanager
def filing_trace(
    *,
    accession: str,
    ticker: str | None = None,
    cik: str | None = None,
    cutoff: str | None = None,
) -> Iterator[trace.Span]:
    tracer = get_tracer()
    with tracer.start_as_current_span("analyze_filing") as span:
        set_attrs(
            span,
            {
                "filing.accession": accession,
                "filing.ticker": ticker,
                "filing.cik": cik,
                "filing.cutoff": cutoff,
            },
        )
        yield span


@contextmanager
def span(name: str, **attrs: Any) -> Iterator[trace.Span]:
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as sp:
        set_attrs(sp, attrs)
        yield sp
