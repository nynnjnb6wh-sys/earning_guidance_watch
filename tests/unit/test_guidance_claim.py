"""GuidanceClaim validation rules."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from guidance_watch.models import FiscalPeriod, GuidanceClaim


def _base_kwargs() -> dict[str, object]:
    return {
        "ticker": "NVDA",
        "cik": "0001045810",
        "accession": "0001045810-24-000001",
        "filing_date": "2024-02-21",
        "accepted_at": datetime(2024, 2, 21, 16, 5, tzinfo=UTC),
        "source_document": "ex99.htm",
        "target_fiscal_period": FiscalPeriod.parse("FY2025Q1"),
        "lower_bound_usd_m": 24000.0,
        "upper_bound_usd_m": 25000.0,
        "unit_in_source": "billions",
        "supporting_quote": "Revenue is expected to be $24.0 billion to $25.0 billion",
        "confidence": 0.85,
    }


@pytest.mark.unit
def test_valid_claim() -> None:
    claim = GuidanceClaim(**_base_kwargs())  # type: ignore[arg-type]
    assert claim.metric == "revenue"
    assert claim.gaap_or_non_gaap == "gaap"


@pytest.mark.unit
def test_inverted_bounds_rejected() -> None:
    kwargs = _base_kwargs()
    kwargs["lower_bound_usd_m"] = 26000.0
    kwargs["upper_bound_usd_m"] = 25000.0
    with pytest.raises(ValidationError):
        GuidanceClaim(**kwargs)  # type: ignore[arg-type]


@pytest.mark.unit
def test_empty_quote_rejected() -> None:
    kwargs = _base_kwargs()
    kwargs["supporting_quote"] = "   "
    with pytest.raises(ValidationError):
        GuidanceClaim(**kwargs)  # type: ignore[arg-type]
