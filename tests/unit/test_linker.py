"""Revision/actual linking rules (D17 — unit-level only)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from guidance_watch.analysis.linker import (
    ActualResult,
    link_claims_for_period,
    never_overwrite_original,
    revision_direction,
)
from guidance_watch.models import FiscalPeriod, GuidanceClaim, RevisionDirection


def _claim(
    *,
    accession: str,
    lower: float,
    upper: float,
    accepted: datetime,
    is_revision: bool = False,
    claim_id: str | None = None,
) -> GuidanceClaim:
    return GuidanceClaim(
        claim_id=claim_id,
        ticker="AMD",
        cik="0000002488",
        accession=accession,
        filing_date=accepted.date().isoformat(),
        accepted_at=accepted,
        source_document="ex99.htm",
        target_fiscal_period=FiscalPeriod.parse("FY2024Q1"),
        lower_bound_usd_m=lower,
        upper_bound_usd_m=upper,
        unit_in_source="millions",
        is_revision=is_revision,
        revision_direction=RevisionDirection.UNKNOWN,
        supporting_quote="Revenue is expected to be $5.0 billion to $5.5 billion",
        confidence=0.8,
    )


@pytest.mark.unit
def test_original_bounds_never_overwritten() -> None:
    original = _claim(
        accession="a1",
        lower=5000,
        upper=5500,
        accepted=datetime(2024, 1, 1, tzinfo=UTC),
        claim_id="orig",
    )
    revision = _claim(
        accession="a2",
        lower=4800,
        upper=5200,
        accepted=datetime(2024, 2, 1, tzinfo=UTC),
        is_revision=True,
        claim_id="rev",
    )
    low, high = never_overwrite_original(original, revision)
    assert (low, high) == (5000, 5500)
    assert revision_direction(original, revision) == RevisionDirection.DOWNWARD


@pytest.mark.unit
def test_link_single_claim_to_actual() -> None:
    claim = _claim(
        accession="a1",
        lower=5000,
        upper=5500,
        accepted=datetime(2024, 1, 1, tzinfo=UTC),
        claim_id="c1",
    )
    actual = ActualResult(
        ticker="AMD",
        cik="0000002488",
        target_fiscal_period=FiscalPeriod.parse("FY2024Q1"),
        actual_revenue_usd_m=5300,
        actual_publication_date=date(2024, 4, 30),
    )
    result = link_claims_for_period([claim], actual)
    assert result.needs_review is False
    assert result.outcome is not None
    assert result.outcome.original_lower_usd_m == 5000
    assert result.outcome.actual_revenue_usd_m == 5300


@pytest.mark.unit
def test_ambiguous_second_claim_needs_review() -> None:
    first = _claim(
        accession="a1",
        lower=5000,
        upper=5500,
        accepted=datetime(2024, 1, 1, tzinfo=UTC),
        claim_id="c1",
    )
    second = _claim(
        accession="a2",
        lower=4800,
        upper=5200,
        accepted=datetime(2024, 2, 1, tzinfo=UTC),
        is_revision=False,  # not explicit
        claim_id="c2",
    )
    actual = ActualResult(
        ticker="AMD",
        cik="0000002488",
        target_fiscal_period=FiscalPeriod.parse("FY2024Q1"),
        actual_revenue_usd_m=5300,
        actual_publication_date=date(2024, 4, 30),
    )
    result = link_claims_for_period([first, second], actual)
    assert result.needs_review is True
    assert result.reason == "ambiguous_revision_link"
    assert result.outcome is None


@pytest.mark.unit
def test_explicit_revision_keeps_original_bounds() -> None:
    first = _claim(
        accession="a1",
        lower=5000,
        upper=5500,
        accepted=datetime(2024, 1, 1, tzinfo=UTC),
        claim_id="c1",
    )
    second = _claim(
        accession="a2",
        lower=4800,
        upper=5200,
        accepted=datetime(2024, 2, 1, tzinfo=UTC),
        is_revision=True,
        claim_id="c2",
    )
    actual = ActualResult(
        ticker="AMD",
        cik="0000002488",
        target_fiscal_period=FiscalPeriod.parse("FY2024Q1"),
        actual_revenue_usd_m=4900,
        actual_publication_date=date(2024, 4, 30),
    )
    result = link_claims_for_period([first, second], actual)
    assert result.outcome is not None
    assert result.outcome.original_lower_usd_m == 5000
    assert result.outcome.latest_lower_usd_m == 4800
    assert result.outcome.downward_revision_occurred is True
    assert result.outcome.revision_count == 1
