"""Pure historical guidance accuracy and revision metrics."""

from __future__ import annotations

from statistics import mean, median

from guidance_watch.models.assessment import QuarterMetrics
from guidance_watch.models.guidance import HistoricalOutcome


def midpoint(lower: float, upper: float) -> float:
    return (lower + upper) / 2.0


def signed_error_pct(actual: float, lower: float, upper: float) -> float:
    mid = midpoint(lower, upper)
    if mid == 0:
        raise ValueError("midpoint must be non-zero to compute signed_error_pct")
    return 100.0 * (actual - mid) / mid


def absolute_error_pct(actual: float, lower: float, upper: float) -> float:
    return abs(signed_error_pct(actual, lower, upper))


def inside_range(actual: float, lower: float, upper: float) -> bool:
    return lower <= actual <= upper


def quarter_metrics(outcome: HistoricalOutcome) -> QuarterMetrics:
    return QuarterMetrics(
        target_fiscal_period_label=outcome.target_fiscal_period.label,
        midpoint_usd_m=midpoint(outcome.original_lower_usd_m, outcome.original_upper_usd_m),
        signed_error_pct=signed_error_pct(
            outcome.actual_revenue_usd_m,
            outcome.original_lower_usd_m,
            outcome.original_upper_usd_m,
        ),
        absolute_error_pct=absolute_error_pct(
            outcome.actual_revenue_usd_m,
            outcome.original_lower_usd_m,
            outcome.original_upper_usd_m,
        ),
        inside_original_range=inside_range(
            outcome.actual_revenue_usd_m,
            outcome.original_lower_usd_m,
            outcome.original_upper_usd_m,
        ),
        inside_latest_range=inside_range(
            outcome.actual_revenue_usd_m,
            outcome.latest_lower_usd_m,
            outcome.latest_upper_usd_m,
        ),
    )


def original_range_hit_rate(outcomes: list[HistoricalOutcome]) -> float | None:
    if not outcomes:
        return None
    hits = sum(
        1
        for o in outcomes
        if inside_range(o.actual_revenue_usd_m, o.original_lower_usd_m, o.original_upper_usd_m)
    )
    return hits / len(outcomes)


def latest_range_hit_rate(outcomes: list[HistoricalOutcome]) -> float | None:
    revised = [o for o in outcomes if o.revision_count > 0]
    if not revised:
        return None
    hits = sum(
        1
        for o in revised
        if inside_range(o.actual_revenue_usd_m, o.latest_lower_usd_m, o.latest_upper_usd_m)
    )
    return hits / len(revised)


def median_signed_error(outcomes: list[HistoricalOutcome]) -> float | None:
    if not outcomes:
        return None
    errors = [
        signed_error_pct(o.actual_revenue_usd_m, o.original_lower_usd_m, o.original_upper_usd_m)
        for o in outcomes
    ]
    return float(median(errors))


def mean_absolute_error(outcomes: list[HistoricalOutcome]) -> float | None:
    if not outcomes:
        return None
    errors = [
        absolute_error_pct(o.actual_revenue_usd_m, o.original_lower_usd_m, o.original_upper_usd_m)
        for o in outcomes
    ]
    return float(mean(errors))


def revision_frequency(outcomes: list[HistoricalOutcome]) -> float | None:
    if not outcomes:
        return None
    revised = sum(1 for o in outcomes if o.revision_count > 0)
    return revised / len(outcomes)


def downward_revision_frequency(outcomes: list[HistoricalOutcome]) -> float | None:
    if not outcomes:
        return None
    downward = sum(1 for o in outcomes if o.downward_revision_occurred)
    return downward / len(outcomes)
