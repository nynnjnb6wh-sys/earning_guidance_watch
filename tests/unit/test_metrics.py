"""Unit tests for pure guidance metrics."""

from __future__ import annotations

from datetime import date

import pytest

from guidance_watch.analysis import (
    absolute_error_pct,
    downward_revision_frequency,
    inside_range,
    mean_absolute_error,
    median_signed_error,
    midpoint,
    original_range_hit_rate,
    revision_frequency,
    signed_error_pct,
)
from guidance_watch.models import FiscalPeriod, HistoricalOutcome


def _outcome(
    *,
    label: str,
    lower: float,
    upper: float,
    actual: float,
    revision_count: int = 0,
    downward: bool = False,
    latest_lower: float | None = None,
    latest_upper: float | None = None,
) -> HistoricalOutcome:
    return HistoricalOutcome(
        guidance_claim_id=f"claim-{label}",
        target_fiscal_period=FiscalPeriod.parse(label),
        original_lower_usd_m=lower,
        original_upper_usd_m=upper,
        latest_lower_usd_m=latest_lower if latest_lower is not None else lower,
        latest_upper_usd_m=latest_upper if latest_upper is not None else upper,
        actual_revenue_usd_m=actual,
        actual_publication_date=date(2024, 1, 1),
        revision_count=revision_count,
        downward_revision_occurred=downward,
        source_documents=["ex99.htm"],
    )


@pytest.mark.unit
def test_midpoint_and_errors() -> None:
    assert midpoint(100.0, 120.0) == 110.0
    # actual 121 vs mid 110 → +10%
    assert signed_error_pct(121.0, 100.0, 120.0) == pytest.approx(10.0)
    assert absolute_error_pct(99.0, 100.0, 120.0) == pytest.approx(abs(100 * (99 - 110) / 110))


@pytest.mark.unit
def test_inside_range_boundaries() -> None:
    assert inside_range(100.0, 100.0, 120.0) is True
    assert inside_range(120.0, 100.0, 120.0) is True
    assert inside_range(99.999, 100.0, 120.0) is False
    assert inside_range(120.001, 100.0, 120.0) is False


@pytest.mark.unit
def test_hit_rate_and_revision_frequency() -> None:
    outcomes = [
        _outcome(label="FY2023Q1", lower=100, upper=110, actual=105),
        _outcome(
            label="FY2023Q2",
            lower=100,
            upper=110,
            actual=120,
            revision_count=1,
            downward=True,
        ),
        _outcome(label="FY2023Q3", lower=100, upper=110, actual=100),
        _outcome(
            label="FY2023Q4",
            lower=100,
            upper=110,
            actual=90,
            revision_count=2,
            downward=False,
        ),
    ]
    assert original_range_hit_rate(outcomes) == pytest.approx(0.5)
    assert revision_frequency(outcomes) == pytest.approx(0.5)
    assert downward_revision_frequency(outcomes) == pytest.approx(0.25)


@pytest.mark.unit
def test_median_signed_error_at_bias_thresholds() -> None:
    # Single quarter: actual such that signed error is exactly +1%
    # mid=100, need actual=101
    plus_one = [_outcome(label="FY2023Q1", lower=90, upper=110, actual=101)]
    assert median_signed_error(plus_one) == pytest.approx(1.0)
    minus_one = [_outcome(label="FY2023Q1", lower=90, upper=110, actual=99)]
    assert median_signed_error(minus_one) == pytest.approx(-1.0)


@pytest.mark.unit
def test_mean_absolute_error() -> None:
    outcomes = [
        _outcome(label="FY2023Q1", lower=90, upper=110, actual=110),  # +10%
        _outcome(label="FY2023Q2", lower=90, upper=110, actual=90),  # -10%
    ]
    assert mean_absolute_error(outcomes) == pytest.approx(10.0)


@pytest.mark.unit
def test_empty_history_returns_none() -> None:
    assert original_range_hit_rate([]) is None
    assert median_signed_error([]) is None
    assert mean_absolute_error([]) is None
    assert revision_frequency([]) is None
    assert downward_revision_frequency([]) is None
