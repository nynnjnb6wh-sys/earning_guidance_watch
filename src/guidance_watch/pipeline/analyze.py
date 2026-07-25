"""Analyze a single accession end-to-end (fixture-friendly vertical slice)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from guidance_watch import AGENT_VERSION, PROMPT_VERSION, SCORING_VERSION
from guidance_watch.analysis.scoring import calculate_assessment
from guidance_watch.config import Settings, get_settings
from guidance_watch.models import (
    AssessmentInput,
    FilingDocument,
    FiscalPeriod,
    GuidanceClaim,
    ReliabilityAssessment,
    RevisionDirection,
    SentimentResult,
)
from guidance_watch.persistence import repository as repo
from guidance_watch.persistence.db import init_db
from guidance_watch.reporting.render import render_json_report, render_markdown_report
from guidance_watch.sec.fixture_client import FixtureSecClient
from guidance_watch.sec.html_text import quote_appears_in_source

# Deterministic extractors for common quarterly GAAP revenue guidance phrasings.
# Explicit A-to-B ranges:
_RANGE_TO_RE = re.compile(
    r"Revenue\s+is\s+expected\s+to\s+be\s+\$?\s*([0-9]+(?:\.[0-9]+)?)\s*"
    r"(billion|million)\s+to\s+\$?\s*([0-9]+(?:\.[0-9]+)?)\s*(billion|million)",
    re.IGNORECASE,
)
# Midpoint ± absolute amount (AMD-style):
_RANGE_PLUSMINUS_ABS_RE = re.compile(
    r"(?:expects\s+)?revenue\s+to\s+be\s+approximately\s+\$?\s*([0-9]+(?:\.[0-9]+)?)\s*"
    r"(billion|million),\s*plus\s+or\s+minus\s+\$?\s*([0-9]+(?:\.[0-9]+)?)\s*"
    r"(billion|million)",
    re.IGNORECASE,
)
# Midpoint ± percent (NVIDIA-style):
_RANGE_PLUSMINUS_PCT_RE = re.compile(
    r"Revenue\s+is\s+expected\s+to\s+be\s+\$?\s*([0-9]+(?:\.[0-9]+)?)\s*"
    r"(billion|million),\s*plus\s+or\s+minus\s+([0-9]+(?:\.[0-9]+)?)\s*%",
    re.IGNORECASE,
)
_QUARTER_WORD = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
}


@dataclass
class AnalyzeResult:
    status: str
    accession: str
    run_id: str | None = None
    detail: str | None = None
    assessment: ReliabilityAssessment | None = None


def _to_usd_m(value: float, unit: str) -> float:
    unit_l = unit.lower()
    if unit_l.startswith("billion"):
        return value * 1000.0
    if unit_l.startswith("million"):
        return value
    raise ValueError(f"Unsupported unit: {unit}")


def _extract_period_near(text: str, anchor_start: int) -> FiscalPeriod | None:
    """Find the fiscal period nearest the guidance quote (look-behind window)."""
    window_start = max(0, anchor_start - 400)
    window = text[window_start : anchor_start + 80]
    fy = re.search(r"\bFY\s*(\d{4})\s*Q\s*([1-4])\b", window, re.IGNORECASE)
    if fy:
        return FiscalPeriod.parse(f"FY{fy.group(1)}Q{fy.group(2)}")
    # NVIDIA-style "second quarter of fiscal 2027" / AMD-style "second quarter of 2026"
    matches = list(
        re.finditer(
            r"\b(first|second|third|fourth)\s+quarter\s+of\s+(?:fiscal\s+)?(\d{4})\b",
            window,
            re.IGNORECASE,
        )
    )
    if not matches:
        # Fall back to first mention in the whole document.
        matches = list(
            re.finditer(
                r"\b(first|second|third|fourth)\s+quarter\s+of\s+(?:fiscal\s+)?(\d{4})\b",
                text,
                re.IGNORECASE,
            )
        )
    if not matches:
        return None
    m = matches[-1]
    q = _QUARTER_WORD[m.group(1).lower()]
    return FiscalPeriod.parse(f"FY{m.group(2)}Q{q}")


def _parse_guidance_bounds(text: str) -> tuple[float, float, str, int] | None:
    """Return (lower_usd_m, upper_usd_m, quote, match_start) or None."""
    m = _RANGE_TO_RE.search(text)
    if m:
        lower = _to_usd_m(float(m.group(1)), m.group(2))
        upper = _to_usd_m(float(m.group(3)), m.group(4))
        return lower, upper, m.group(0), m.start()

    m = _RANGE_PLUSMINUS_ABS_RE.search(text)
    if m:
        mid = _to_usd_m(float(m.group(1)), m.group(2))
        delta = _to_usd_m(float(m.group(3)), m.group(4))
        return mid - delta, mid + delta, m.group(0), m.start()

    m = _RANGE_PLUSMINUS_PCT_RE.search(text)
    if m:
        mid = _to_usd_m(float(m.group(1)), m.group(2))
        pct = float(m.group(3)) / 100.0
        return mid * (1.0 - pct), mid * (1.0 + pct), m.group(0), m.start()

    return None


def extract_guidance_from_text(
    *,
    text: str,
    meta_accession: str,
    meta_cik: str,
    meta_ticker: str,
    meta_filing_date: str,
    meta_accepted_at: object,
    source_document: str,
) -> GuidanceClaim | None:
    parsed = _parse_guidance_bounds(text)
    if parsed is None:
        return None
    lower, upper, quote, start = parsed
    period = _extract_period_near(text, start)
    if period is None:
        return None
    if not quote_appears_in_source(quote, text):
        return None
    from datetime import datetime

    accepted_at = meta_accepted_at
    if isinstance(accepted_at, str):
        accepted_at = datetime.fromisoformat(accepted_at.replace("Z", "+00:00"))
    return GuidanceClaim(
        ticker=meta_ticker,
        cik=meta_cik,
        accession=meta_accession,
        filing_date=meta_filing_date,
        accepted_at=accepted_at,  # type: ignore[arg-type]
        source_document=source_document,
        target_fiscal_period=period,
        lower_bound_usd_m=round(lower, 6),
        upper_bound_usd_m=round(upper, 6),
        unit_in_source="normalized_to_usd_millions",
        is_revision=False,
        revision_direction=RevisionDirection.UNKNOWN,
        supporting_quote=quote,
        confidence=0.8,
        needs_review=False,
    )


def select_exhibit99(documents: list[FilingDocument]) -> str | None:
    def score(filename: str) -> tuple[int, str]:
        lower = filename.lower()
        # Lower score = better preference.
        if "ex99" in lower or re.search(r"ex[-_]?99", lower) or "991" in lower:
            return (0, lower)
        if "pr.htm" in lower or "press" in lower or "earningsrelease" in lower:
            return (1, lower)
        if "cfocommentary" in lower or "earnings" in lower:
            return (2, lower)
        return (5, lower)

    html_docs = [d for d in documents if d.is_html]
    if not html_docs:
        return None
    html_docs.sort(key=lambda d: score(d.filename))
    best = html_docs[0]
    # If best is only a cover 8-K and a better exhibit exists, prefer exhibit-ish names.
    if score(best.filename)[0] >= 5:
        return best.filename
    return best.filename


def analyze_accession(
    accession: str,
    *,
    fixtures_root: Path,
    settings: Settings | None = None,
) -> AnalyzeResult:
    settings = settings or get_settings()
    conn = init_db(settings.db_path)
    try:
        existing = repo.get_analysis_run(conn, accession)
        if existing is not None:
            repo.insert_job_attempt(
                conn,
                accession=accession,
                status="ignored",
                detail="already processed",
            )
            conn.commit()
            return AnalyzeResult(
                status="already_processed",
                accession=accession,
                run_id=str(existing["run_id"]),
                detail="already processed",
            )

        client = FixtureSecClient(fixtures_root)
        meta = client.get_filing_metadata(accession)
        repo.upsert_filing(conn, meta)
        repo.insert_job_attempt(conn, accession=accession, status="running")

        documents = client.list_filing_documents(accession)
        filename = select_exhibit99(documents)
        if filename is None:
            run_id = repo.insert_analysis_run(
                conn,
                accession=accession,
                ticker=meta.ticker,
                cik=meta.cik,
                status="ignored",
                prompt_version=PROMPT_VERSION,
                agent_version=AGENT_VERSION,
                scoring_version=SCORING_VERSION,
                model_identifier="deterministic-extractor-v1",
                assessment=None,
                ignore_reason="no_html_exhibit",
            )
            conn.commit()
            return AnalyzeResult(status="ignored", accession=accession, run_id=run_id)

        content = client.fetch_filing_document(accession, filename)
        claim = extract_guidance_from_text(
            text=content.text,
            meta_accession=meta.accession,
            meta_cik=meta.cik,
            meta_ticker=meta.ticker or "UNKNOWN",
            meta_filing_date=meta.filing_date,
            meta_accepted_at=meta.accepted_at,
            source_document=filename,
        )
        if claim is None:
            run_id = repo.insert_analysis_run(
                conn,
                accession=accession,
                ticker=meta.ticker,
                cik=meta.cik,
                status="ignored",
                prompt_version=PROMPT_VERSION,
                agent_version=AGENT_VERSION,
                scoring_version=SCORING_VERSION,
                model_identifier="deterministic-extractor-v1",
                assessment=None,
                ignore_reason="no_quarterly_gaap_revenue_guidance",
            )
            conn.commit()
            return AnalyzeResult(status="ignored", accession=accession, run_id=run_id)

        # Slice 2: empty history + fake sentiment so assessment path is exercised.
        sentiment = SentimentResult.from_probabilities(
            model_name="fake-sentiment",
            model_revision="slice2",
            positive_probability=0.4,
            neutral_probability=0.4,
            negative_probability=0.2,
            analyzed_text_hash="slice2-placeholder",
        )
        assessment = calculate_assessment(
            AssessmentInput(
                current_claim=claim,
                history=[],
                current_sentiment=sentiment,
                historical_tone_scores=[],
            )
        )

        claim_id = repo.insert_guidance_claim(conn, claim)
        claim.claim_id = claim_id
        run_id = repo.insert_analysis_run(
            conn,
            accession=accession,
            ticker=meta.ticker,
            cik=meta.cik,
            status="completed",
            prompt_version=PROMPT_VERSION,
            agent_version=AGENT_VERSION,
            scoring_version=SCORING_VERSION,
            model_identifier="deterministic-extractor-v1",
            assessment=assessment,
        )

        json_body = render_json_report(claim, assessment)
        md_body = render_markdown_report(claim, assessment)
        reports_dir = settings.reports_dir / (meta.ticker or "UNKNOWN") / accession
        reports_dir.mkdir(parents=True, exist_ok=True)
        json_path = reports_dir / "report.json"
        md_path = reports_dir / "report.md"
        json_path.write_text(json_body, encoding="utf-8")
        md_path.write_text(md_body, encoding="utf-8")
        repo.insert_report(
            conn,
            run_id=run_id,
            accession=accession,
            fmt="json",
            body=json_body,
            path=str(json_path),
        )
        repo.insert_report(
            conn,
            run_id=run_id,
            accession=accession,
            fmt="markdown",
            body=md_body,
            path=str(md_path),
        )
        repo.insert_job_attempt(conn, accession=accession, status="completed")
        conn.commit()
        return AnalyzeResult(
            status="completed",
            accession=accession,
            run_id=run_id,
            assessment=assessment,
        )
    finally:
        conn.close()
