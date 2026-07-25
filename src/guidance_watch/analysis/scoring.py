"""Heuristic historical-reliability scoring (pure, deterministic)."""

from __future__ import annotations

from statistics import median

from guidance_watch.analysis import bias as bias_mod
from guidance_watch.analysis import metrics as metrics_mod
from guidance_watch.models.assessment import (
    AssessmentInput,
    ReliabilityAssessment,
    ReliabilityLabel,
)

MIN_QUARTERS_FOR_LABEL = 4
SAMPLE_SIZE_CAVEAT_BELOW = 8
TONE_UNUSUAL_ABS = 0.30


def clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def map_total_to_label(total: float) -> ReliabilityLabel:
    if total >= 75.0:
        return ReliabilityLabel.HIGH
    if total >= 50.0:
        return ReliabilityLabel.MEDIUM
    return ReliabilityLabel.LOW


def calculate_assessment(inp: AssessmentInput) -> ReliabilityAssessment:
    """Compute descriptive stats and heuristic reliability score.

    - Fewer than 4 usable quarters → `insufficient_history` (stats still shown).
    - Missing sentiment baseline → sentiment components unavailable; total not calculated.
    - 4–7 quarters → normal label with `sample_size_caveat=True`.
    """
    history = list(inp.history)
    usable = len(history)
    limitations: list[str] = []

    q_metrics = [metrics_mod.quarter_metrics(o) for o in history]
    original_hit = metrics_mod.original_range_hit_rate(history)
    latest_hit = metrics_mod.latest_range_hit_rate(history)
    med_signed = metrics_mod.median_signed_error(history)
    mae = metrics_mod.mean_absolute_error(history)
    rev_freq = metrics_mod.revision_frequency(history)
    down_freq = metrics_mod.downward_revision_frequency(history)
    tendency = bias_mod.observed_tendency(med_signed)

    sample_caveat = usable < SAMPLE_SIZE_CAVEAT_BELOW
    if sample_caveat and usable > 0:
        limitations.append(
            f"Only {usable} completed historical quarter(s); treat results as an "
            "observed historical tendency, not a strong reliability claim."
        )

    current_tone = inp.current_sentiment.tone_score if inp.current_sentiment else None
    hist_tones = list(inp.historical_tone_scores)
    hist_median_tone = float(median(hist_tones)) if hist_tones else None
    tone_anomaly: float | None = None
    tone_unusual: bool | None = None
    if current_tone is not None and hist_median_tone is not None:
        tone_anomaly = current_tone - hist_median_tone
        tone_unusual = abs(tone_anomaly) > TONE_UNUSUAL_ABS

    sentiment_available = current_tone is not None and hist_median_tone is not None
    if not sentiment_available:
        limitations.append(
            "Sentiment baseline unavailable; overall heuristic score was not calculated."
        )

    historical_hit_score: float | None = None
    revision_score: float | None = None
    tone_consistency_score: float | None = None
    total_score: float | None = None
    label: ReliabilityLabel

    if usable < MIN_QUARTERS_FOR_LABEL:
        label = ReliabilityLabel.INSUFFICIENT_HISTORY
        limitations.append(
            f"Fewer than {MIN_QUARTERS_FOR_LABEL} completed historical quarters; "
            "no high/medium/low reliability label."
        )
        if original_hit is not None:
            historical_hit_score = 100.0 * original_hit
        if down_freq is not None:
            revision_score = 100.0 * (1.0 - down_freq)
        if sentiment_available:
            assert current_tone is not None and hist_median_tone is not None
            tone_consistency_score = clip(
                100.0 - 50.0 * abs(current_tone - hist_median_tone), 0.0, 100.0
            )
        # total remains None when insufficient history or sentiment missing
        if usable >= MIN_QUARTERS_FOR_LABEL and sentiment_available:
            pass  # unreachable; kept for clarity
    elif not sentiment_available:
        label = ReliabilityLabel.UNAVAILABLE
        if original_hit is not None:
            historical_hit_score = 100.0 * original_hit
        if down_freq is not None:
            revision_score = 100.0 * (1.0 - down_freq)
        # Do not reweight remaining components; total stays None.
    else:
        assert original_hit is not None and down_freq is not None
        assert current_tone is not None and hist_median_tone is not None
        historical_hit_score = 100.0 * original_hit
        revision_score = 100.0 * (1.0 - down_freq)
        tone_consistency_score = clip(
            100.0 - 50.0 * abs(current_tone - hist_median_tone), 0.0, 100.0
        )
        total_score = (
            0.60 * historical_hit_score + 0.25 * revision_score + 0.15 * tone_consistency_score
        )
        label = map_total_to_label(total_score)

    return ReliabilityAssessment(
        usable_quarters=usable,
        original_range_hit_rate=original_hit,
        latest_range_hit_rate=latest_hit,
        median_signed_error_pct=med_signed,
        mean_absolute_error_pct=mae,
        revision_frequency=rev_freq,
        downward_revision_frequency=down_freq,
        observed_tendency=tendency,
        sample_size_caveat=sample_caveat,
        current_tone_score=current_tone,
        historical_median_tone=hist_median_tone,
        tone_anomaly=tone_anomaly,
        tone_unusual=tone_unusual,
        historical_hit_score=historical_hit_score,
        revision_score=revision_score,
        tone_consistency_score=tone_consistency_score,
        total_score=total_score,
        label=label,
        quarter_metrics=q_metrics,
        limitations=limitations,
    )
