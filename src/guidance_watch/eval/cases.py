"""Fixture-based evaluation case definitions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures"


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    description: str
    accession: str
    expect_relevant: bool
    expect_source_document: str | None = None
    expect_lower_usd_m: float | None = None
    expect_upper_usd_m: float | None = None
    expect_period: str | None = None
    expect_label: str | None = None
    category: str = "e2e"


EVAL_CASES: tuple[EvalCase, ...] = (
    EvalCase(
        case_id="case01_relevant_ex99",
        description="Relevant 8-K with one HTML Exhibit 99 and one quarterly revenue range",
        accession="0000002488-24-000100",
        expect_relevant=True,
        expect_source_document="ex99-1.htm",
        expect_lower_usd_m=5400.0,
        expect_upper_usd_m=6000.0,
        expect_period="FY2024Q1",
    ),
    EvalCase(
        case_id="case02_irrelevant",
        description="Irrelevant 8-K with no guidance",
        accession="0000002488-24-000200",
        expect_relevant=False,
    ),
    EvalCase(
        case_id="case03_multi_exhibit",
        description="Several Exhibit 99 documents where only one is relevant",
        accession="0000002488-24-000300",
        expect_relevant=True,
        expect_source_document="ex99-2.htm",
        expect_lower_usd_m=1000.0,
        expect_upper_usd_m=1200.0,
        expect_period="FY2024Q2",
    ),
    EvalCase(
        case_id="case04_quarter_and_full_year",
        description="Quarterly and full-year guidance in the same release",
        accession="0000002488-24-000400",
        expect_relevant=True,
        expect_lower_usd_m=2000.0,
        expect_upper_usd_m=2200.0,
        expect_period="FY2024Q3",
    ),
    EvalCase(
        case_id="case05_fiscal_vs_calendar",
        description="Fiscal quarter differing from the calendar quarter of the filing",
        accession="0000002488-24-000500",
        expect_relevant=True,
        expect_lower_usd_m=3000.0,
        expect_upper_usd_m=3200.0,
        expect_period="FY2025Q1",
        category="fiscal_calendar",
    ),
    EvalCase(
        case_id="case06_billions_units",
        description="Units expressed as billions",
        accession="0000002488-24-000100",
        expect_relevant=True,
        expect_lower_usd_m=5400.0,
        expect_upper_usd_m=6000.0,
    ),
    EvalCase(
        case_id="case07_actual_bounds",
        description="Actual revenue just inside or outside a range",
        accession="n/a",
        expect_relevant=True,
        category="actual_bounds",
    ),
    EvalCase(
        case_id="case08_post_cutoff",
        description="A post-cutoff document that must be rejected",
        accession="n/a",
        expect_relevant=True,
        category="temporal",
    ),
    EvalCase(
        case_id="case09_duplicate",
        description="Duplicate accession processing",
        accession="0000002488-24-000100",
        expect_relevant=True,
        category="dedupe",
    ),
    EvalCase(
        case_id="case10_http_retry",
        description="Temporary HTTP failure followed by a successful retry",
        accession="n/a",
        expect_relevant=True,
        category="http_retry",
    ),
    EvalCase(
        case_id="case11_missing_sentiment_baseline",
        description="Missing sentiment baseline",
        accession="0000002488-24-000100",
        expect_relevant=True,
        category="sentiment_baseline",
    ),
    EvalCase(
        case_id="case12_insufficient_history",
        description="Too little history for a reliability label",
        accession="0000002488-24-000100",
        expect_relevant=True,
        expect_label="insufficient_history",
        category="thin_history",
    ),
    EvalCase(
        case_id="case13_bad_quote",
        description="Supporting quote that does not appear in the source",
        accession="0000002488-24-000100",
        expect_relevant=True,
        category="quote",
    ),
)
