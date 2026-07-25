"""Guidance claim, outcome, and sentiment models."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from guidance_watch.models.periods import FiscalPeriod


class RevisionDirection(StrEnum):
    UPWARD = "upward"
    DOWNWARD = "downward"
    UNCHANGED = "unchanged"
    UNKNOWN = "unknown"


class GuidanceClaim(BaseModel):
    """Extracted numerical quarterly GAAP revenue guidance claim."""

    ticker: str
    cik: str
    accession: str
    filing_date: str
    accepted_at: datetime
    source_document: str
    target_fiscal_period: FiscalPeriod
    metric: Literal["revenue"] = "revenue"
    gaap_or_non_gaap: Literal["gaap"] = "gaap"
    lower_bound_usd_m: float
    upper_bound_usd_m: float
    currency: Literal["USD"] = "USD"
    unit_in_source: str
    is_revision: bool = False
    revision_direction: RevisionDirection = RevisionDirection.UNKNOWN
    supporting_quote: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    needs_review: bool = False
    claim_id: str | None = None

    @model_validator(mode="after")
    def _bounds_ordered(self) -> GuidanceClaim:
        if self.lower_bound_usd_m > self.upper_bound_usd_m:
            raise ValueError("lower_bound_usd_m must be <= upper_bound_usd_m")
        if not self.supporting_quote.strip():
            raise ValueError("supporting_quote must be non-empty")
        return self


class HistoricalOutcome(BaseModel):
    """Linked original/latest guidance and actual revenue for one quarter."""

    guidance_claim_id: str
    target_fiscal_period: FiscalPeriod
    original_lower_usd_m: float
    original_upper_usd_m: float
    latest_lower_usd_m: float
    latest_upper_usd_m: float
    actual_revenue_usd_m: float
    actual_publication_date: date
    revision_count: int = Field(default=0, ge=0)
    downward_revision_occurred: bool = False
    source_documents: list[str] = Field(default_factory=list)


class SentimentResult(BaseModel):
    model_name: str
    model_revision: str
    positive_probability: float = Field(..., ge=0.0, le=1.0)
    neutral_probability: float = Field(..., ge=0.0, le=1.0)
    negative_probability: float = Field(..., ge=0.0, le=1.0)
    tone_score: float
    analyzed_text_hash: str

    @field_validator("tone_score")
    @classmethod
    def _tone_in_range(cls, value: float) -> float:
        if value < -1.0 or value > 1.0:
            raise ValueError("tone_score must be in [-1, 1]")
        return value

    @classmethod
    def from_probabilities(
        cls,
        *,
        model_name: str,
        model_revision: str,
        positive_probability: float,
        neutral_probability: float,
        negative_probability: float,
        analyzed_text_hash: str,
    ) -> SentimentResult:
        return cls(
            model_name=model_name,
            model_revision=model_revision,
            positive_probability=positive_probability,
            neutral_probability=neutral_probability,
            negative_probability=negative_probability,
            tone_score=positive_probability - negative_probability,
            analyzed_text_hash=analyzed_text_hash,
        )
