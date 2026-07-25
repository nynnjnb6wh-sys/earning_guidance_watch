"""Assessment input/output models."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from guidance_watch.models.guidance import GuidanceClaim, HistoricalOutcome, SentimentResult


class ReliabilityLabel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INSUFFICIENT_HISTORY = "insufficient_history"
    UNAVAILABLE = "unavailable"


class BiasTendency(StrEnum):
    CONSERVATIVE = "conservative"
    OPTIMISTIC = "optimistic"
    APPROXIMATELY_CENTERED = "approximately_centered"


class QuarterMetrics(BaseModel):
    target_fiscal_period_label: str
    midpoint_usd_m: float
    signed_error_pct: float
    absolute_error_pct: float
    inside_original_range: bool
    inside_latest_range: bool


class AssessmentInput(BaseModel):
    current_claim: GuidanceClaim
    history: list[HistoricalOutcome] = Field(default_factory=list)
    current_sentiment: SentimentResult | None = None
    historical_tone_scores: list[float] = Field(default_factory=list)


class ReliabilityAssessment(BaseModel):
    usable_quarters: int
    original_range_hit_rate: float | None = None
    latest_range_hit_rate: float | None = None
    median_signed_error_pct: float | None = None
    mean_absolute_error_pct: float | None = None
    revision_frequency: float | None = None
    downward_revision_frequency: float | None = None
    observed_tendency: BiasTendency | None = None
    sample_size_caveat: bool = False

    current_tone_score: float | None = None
    historical_median_tone: float | None = None
    tone_anomaly: float | None = None
    tone_unusual: bool | None = None

    historical_hit_score: float | None = None
    revision_score: float | None = None
    tone_consistency_score: float | None = None
    total_score: float | None = None
    label: ReliabilityLabel

    quarter_metrics: list[QuarterMetrics] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
