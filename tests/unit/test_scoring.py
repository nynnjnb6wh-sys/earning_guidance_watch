"""Boundary tests for heuristic reliability scoring."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from guidance_watch.analysis import calculate_assessment, map_total_to_label, observed_tendency
from guidance_watch.models import (
    AssessmentInput,
    BiasTendency,
    FiscalPeriod,
    GuidanceClaim,
    HistoricalOutcome,
    ReliabilityLabel,
    SentimentResult,
)


def _claim() -> GuidanceClaim:
    return GuidanceClaim(
        ticker="AMD",
        cik="0000002488",
        accession="0000002488-24-000001",
        filing_date="2024-01-30",
        accepted_at=datetime(2024, 1, 30, 16, 5, tzinfo=UTC),
        source_document="ex99.htm",
        target_fiscal_period=FiscalPeriod.parse("FY2024Q1"),
        lower_bound_usd_m=5000.0,
        upper_bound_usd_m=5400.0,
        unit_in_source="millions",
        supporting_quote="Revenue is expected to be $5.0 to $5.4 billion",
        confidence=0.9,
    )


def _outcome(
    idx: int,
    *,
    hit: bool = True,
    downward: bool = False,
    revision_count: int = 0,
) -> HistoricalOutcome:
    # mid=100; hit => actual 100; miss => actual 130
    actual = 100.0 if hit else 130.0
    return HistoricalOutcome(
        guidance_claim_id=f"c{idx}",
        target_fiscal_period=FiscalPeriod.parse(f"FY2023Q{(idx % 4) + 1}"),
        original_lower_usd_m=90.0,
        original_upper_usd_m=110.0,
        latest_lower_usd_m=90.0,
        latest_upper_usd_m=110.0,
        actual_revenue_usd_m=actual,
        actual_publication_date=date(2023, 1, 1),
        revision_count=revision_count,
        downward_revision_occurred=downward,
        source_documents=["ex99.htm"],
    )


def _sentiment(tone: float = 0.1) -> SentimentResult:
    # tone = pos - neg; choose simple probs that sum reasonably
    if tone >= 0:
        pos, neg = tone, 0.0
        neu = 1.0 - pos - neg
    else:
        pos, neg = 0.0, -tone
        neu = 1.0 - pos - neg
    return SentimentResult.from_probabilities(
        model_name="fake",
        model_revision="test",
        positive_probability=pos,
        neutral_probability=neu,
        negative_probability=neg,
        analyzed_text_hash="abc",
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("total", "expected"),
    [
        (49.999, ReliabilityLabel.LOW),
        (50.0, ReliabilityLabel.MEDIUM),
        (74.999, ReliabilityLabel.MEDIUM),
        (75.0, ReliabilityLabel.HIGH),
        (100.0, ReliabilityLabel.HIGH),
        (0.0, ReliabilityLabel.LOW),
    ],
)
def test_map_total_boundaries(total: float, expected: ReliabilityLabel) -> None:
    assert map_total_to_label(total) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("median_signed", "expected"),
    [
        (1.0, BiasTendency.APPROXIMATELY_CENTERED),
        (-1.0, BiasTendency.APPROXIMATELY_CENTERED),
        (1.0001, BiasTendency.CONSERVATIVE),
        (-1.0001, BiasTendency.OPTIMISTIC),
        (0.0, BiasTendency.APPROXIMATELY_CENTERED),
        (None, None),
    ],
)
def test_bias_thresholds(median_signed: float | None, expected: BiasTendency | None) -> None:
    assert observed_tendency(median_signed) == expected


@pytest.mark.unit
def test_insufficient_history_three_quarters() -> None:
    history = [_outcome(i) for i in range(3)]
    result = calculate_assessment(
        AssessmentInput(
            current_claim=_claim(),
            history=history,
            current_sentiment=_sentiment(0.1),
            historical_tone_scores=[0.0, 0.05, 0.1],
        )
    )
    assert result.usable_quarters == 3
    assert result.label == ReliabilityLabel.INSUFFICIENT_HISTORY
    assert result.total_score is None
    assert result.sample_size_caveat is True
    assert result.original_range_hit_rate == pytest.approx(1.0)


@pytest.mark.unit
def test_four_quarters_gets_label_with_caveat() -> None:
    # Perfect hits, no downward revisions, identical tone → total = 100
    history = [_outcome(i) for i in range(4)]
    result = calculate_assessment(
        AssessmentInput(
            current_claim=_claim(),
            history=history,
            current_sentiment=_sentiment(0.2),
            historical_tone_scores=[0.2, 0.2, 0.2, 0.2],
        )
    )
    assert result.usable_quarters == 4
    assert result.label == ReliabilityLabel.HIGH
    assert result.total_score == pytest.approx(100.0)
    assert result.sample_size_caveat is True


@pytest.mark.unit
def test_zero_usable_quarters() -> None:
    result = calculate_assessment(
        AssessmentInput(
            current_claim=_claim(),
            history=[],
            current_sentiment=_sentiment(0.1),
            historical_tone_scores=[],
        )
    )
    assert result.usable_quarters == 0
    assert result.label == ReliabilityLabel.INSUFFICIENT_HISTORY
    assert result.total_score is None
    assert result.original_range_hit_rate is None


@pytest.mark.unit
def test_missing_sentiment_no_imputation() -> None:
    history = [_outcome(i) for i in range(4)]
    result = calculate_assessment(
        AssessmentInput(
            current_claim=_claim(),
            history=history,
            current_sentiment=_sentiment(0.1),
            historical_tone_scores=[],  # baseline missing
        )
    )
    assert result.label == ReliabilityLabel.UNAVAILABLE
    assert result.total_score is None
    assert result.tone_consistency_score is None
    assert result.historical_hit_score == pytest.approx(100.0)
    assert any("Sentiment baseline unavailable" in lim for lim in result.limitations)


@pytest.mark.unit
def test_total_score_at_label_boundaries() -> None:
    # Construct component scores so total is exactly 50 and 75.
    # total = 0.60*hit + 0.25*rev + 0.15*tone
    # Perfect rev and tone: total = 0.60*hit + 0.25*100 + 0.15*100 = 0.60*hit + 40
    # For total=50: hit = (50-40)/0.60 = 16.666... → hit_rate = 0.1666...
    # Easier: use 6 hit / 6 miss? Let's pick known rates.
    #
    # 3 hits / 6 quarters → hit_rate=0.5 → hit_score=50
    # no downward → rev=100
    # tone equal → tone=100
    # total = 0.6*50 + 0.25*100 + 0.15*100 = 30+25+15 = 70 (medium)
    #
    # For exactly 50: hit_score=h, rev=100, tone=100 → 0.6h+40=50 → h=16.666...
    # 1 hit of 6 = 16.666... ✓
    history_50 = [_outcome(i, hit=(i == 0)) for i in range(6)]
    result_50 = calculate_assessment(
        AssessmentInput(
            current_claim=_claim(),
            history=history_50,
            current_sentiment=_sentiment(0.0),
            historical_tone_scores=[0.0] * 6,
        )
    )
    assert result_50.total_score == pytest.approx(50.0)
    assert result_50.label == ReliabilityLabel.MEDIUM

    # For exactly 75: 0.6h + 40 = 75 → h = 58.333... → 7/12 = 0.58333
    history_75 = [_outcome(i, hit=(i < 7)) for i in range(12)]
    # Wait we only use first N; need usable=8 max typically but 12 is fine
    # Actually 7/12 * 100 = 58.333..., total = 0.6*58.333 + 40 = 75 exactly
    result_75 = calculate_assessment(
        AssessmentInput(
            current_claim=_claim(),
            history=history_75[:12],
            current_sentiment=_sentiment(0.0),
            historical_tone_scores=[0.0] * 12,
        )
    )
    assert result_75.total_score == pytest.approx(75.0)
    assert result_75.label == ReliabilityLabel.HIGH


@pytest.mark.unit
def test_tone_anomaly_flag() -> None:
    history = [_outcome(i) for i in range(4)]
    result = calculate_assessment(
        AssessmentInput(
            current_claim=_claim(),
            history=history,
            current_sentiment=_sentiment(0.5),
            historical_tone_scores=[0.0, 0.0, 0.0, 0.0],
        )
    )
    assert result.tone_anomaly == pytest.approx(0.5)
    assert result.tone_unusual is True
