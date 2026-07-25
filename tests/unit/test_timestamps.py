"""EDGAR timestamp parsing."""

from __future__ import annotations

from datetime import UTC

import pytest

from guidance_watch.sec.timestamps import parse_edgar_accepted_at


@pytest.mark.unit
def test_naive_eastern_converted_to_utc() -> None:
    # 16:05 Eastern in January is UTC-5 → 21:05 UTC
    dt = parse_edgar_accepted_at("2024-01-30T16:05:12.000")
    assert dt.tzinfo is not None
    assert dt.astimezone(UTC).hour == 21
    assert dt.astimezone(UTC).minute == 5


@pytest.mark.unit
def test_zulu_passthrough() -> None:
    dt = parse_edgar_accepted_at("2024-01-30T21:05:12Z")
    assert dt.astimezone(UTC).hour == 21
