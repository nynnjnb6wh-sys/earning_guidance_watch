"""Observed historical guidance tendency (bias) labeling."""

from __future__ import annotations

from guidance_watch.models.assessment import BiasTendency

BIAS_THRESHOLD_PCT = 1.0


def observed_tendency(median_signed_error_pct: float | None) -> BiasTendency | None:
    """Label observed historical tendency from median signed error.

    Positive signed error means actual exceeded midpoint (conservative guidance).
    Negative signed error means actual fell short (optimistic guidance).
    """
    if median_signed_error_pct is None:
        return None
    if median_signed_error_pct > BIAS_THRESHOLD_PCT:
        return BiasTendency.CONSERVATIVE
    if median_signed_error_pct < -BIAS_THRESHOLD_PCT:
        return BiasTendency.OPTIMISTIC
    return BiasTendency.APPROXIMATELY_CENTERED


def tendency_phrase(tendency: BiasTendency | None, usable_quarters: int) -> str:
    if tendency is None:
        return "observed historical tendency unavailable"
    base = f"observed historical tendency: {tendency.value}"
    if usable_quarters < 8:
        return f"{base} (based on {usable_quarters} completed quarter(s); interpret cautiously)"
    return base
