"""Guidance–actual linking and best-effort revision linking (D17)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from guidance_watch.models import (
    FiscalPeriod,
    GuidanceClaim,
    HistoricalOutcome,
    RevisionDirection,
)


@dataclass
class ActualResult:
    ticker: str
    cik: str
    target_fiscal_period: FiscalPeriod
    actual_revenue_usd_m: float
    actual_publication_date: date
    source: str = "seed"


@dataclass
class LinkResult:
    outcome: HistoricalOutcome | None
    needs_review: bool
    reason: str | None = None


def revision_direction(prior: GuidanceClaim, current: GuidanceClaim) -> RevisionDirection:
    prior_mid = (prior.lower_bound_usd_m + prior.upper_bound_usd_m) / 2.0
    curr_mid = (current.lower_bound_usd_m + current.upper_bound_usd_m) / 2.0
    if curr_mid > prior_mid:
        return RevisionDirection.UPWARD
    if curr_mid < prior_mid:
        return RevisionDirection.DOWNWARD
    return RevisionDirection.UNCHANGED


def link_claims_for_period(
    claims: list[GuidanceClaim],
    actual: ActualResult | None,
) -> LinkResult:
    """Link original/latest guidance for one period to an actual.

    Ambiguous cases (multiple unrelated claims, missing actual, conflicting
    revision signals) become needs_review — never guessed (D17).
    """
    if not claims:
        return LinkResult(None, needs_review=True, reason="no_claims")
    if actual is None:
        return LinkResult(None, needs_review=True, reason="missing_actual")

    # Sort by accepted_at ascending — earliest is original guidance.
    ordered = sorted(claims, key=lambda c: c.accepted_at)
    periods = {c.target_fiscal_period.label for c in ordered}
    if len(periods) != 1:
        return LinkResult(None, needs_review=True, reason="mixed_target_periods")

    original = ordered[0]
    latest = ordered[-1]
    revision_count = max(0, len(ordered) - 1)

    # Ambiguous if a later claim is not an explicit revision and bounds differ oddly
    downward = False
    if revision_count > 0:
        for prev, curr in zip(ordered, ordered[1:], strict=False):
            if curr.is_revision is False and (
                curr.lower_bound_usd_m != prev.lower_bound_usd_m
                or curr.upper_bound_usd_m != prev.upper_bound_usd_m
            ):
                # Second claim for same period without is_revision flag → review
                return LinkResult(
                    None,
                    needs_review=True,
                    reason="ambiguous_revision_link",
                )
            direction = revision_direction(prev, curr)
            if direction == RevisionDirection.DOWNWARD:
                downward = True

    claim_id = original.claim_id or f"{original.accession}:{original.target_fiscal_period.label}"
    outcome = HistoricalOutcome(
        guidance_claim_id=claim_id,
        target_fiscal_period=original.target_fiscal_period,
        original_lower_usd_m=original.lower_bound_usd_m,
        original_upper_usd_m=original.upper_bound_usd_m,
        latest_lower_usd_m=latest.lower_bound_usd_m,
        latest_upper_usd_m=latest.upper_bound_usd_m,
        actual_revenue_usd_m=actual.actual_revenue_usd_m,
        actual_publication_date=actual.actual_publication_date,
        revision_count=revision_count,
        downward_revision_occurred=downward,
        source_documents=sorted({c.source_document for c in ordered}),
    )
    return LinkResult(outcome=outcome, needs_review=False)


def never_overwrite_original(
    original: GuidanceClaim, revision: GuidanceClaim
) -> tuple[float, float]:
    """Return bounds that must remain the original's (unit-test helper)."""
    _ = revision
    return original.lower_bound_usd_m, original.upper_bound_usd_m
