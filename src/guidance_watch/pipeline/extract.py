"""Deterministic Exhibit 99 guidance extraction helpers."""

from __future__ import annotations

import re
from datetime import datetime

from guidance_watch.models import FilingDocument, FiscalPeriod, GuidanceClaim, RevisionDirection
from guidance_watch.sec.html_text import quote_appears_in_source

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


def _exhibit_score(filename: str) -> tuple[int, str]:
    lower = filename.lower()
    # Lower score = better preference.
    if "ex99" in lower or re.search(r"ex[-_]?99", lower) or "991" in lower:
        return (0, lower)
    if "pr.htm" in lower or "press" in lower or "earningsrelease" in lower:
        return (1, lower)
    if "cfocommentary" in lower or "earnings" in lower:
        return (2, lower)
    return (5, lower)


def rank_exhibit_candidates(documents: list[FilingDocument]) -> list[str]:
    """Return HTML attachment filenames ordered by Exhibit 99 preference."""
    html_docs = [d for d in documents if d.is_html]
    if not html_docs:
        return []
    preferred = [d for d in html_docs if _exhibit_score(d.filename)[0] < 5]
    pool = preferred or html_docs
    pool = sorted(pool, key=lambda d: _exhibit_score(d.filename))
    return [d.filename for d in pool]


def select_exhibit99(documents: list[FilingDocument]) -> str | None:
    ranked = rank_exhibit_candidates(documents)
    return ranked[0] if ranked else None
