"""Real-world ± guidance phrasing used by AMD/NVIDIA."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from guidance_watch.pipeline.analyze import extract_guidance_from_text


@pytest.mark.unit
def test_nvidia_plus_minus_percent() -> None:
    text = (
        "NVIDIA's outlook for the second quarter of fiscal 2027 is as follows: "
        "Revenue is expected to be $91.0 billion, plus or minus 2%."
    )
    claim = extract_guidance_from_text(
        text=text,
        meta_accession="0001045810-26-000051",
        meta_cik="0001045810",
        meta_ticker="NVDA",
        meta_filing_date="2026-05-20",
        meta_accepted_at=datetime(2026, 5, 20, 16, 5, tzinfo=UTC),
        source_document="q1fy27pr.htm",
    )
    assert claim is not None
    assert claim.target_fiscal_period.label == "FY2027Q2"
    assert claim.lower_bound_usd_m == pytest.approx(91000 * 0.98)
    assert claim.upper_bound_usd_m == pytest.approx(91000 * 1.02)


@pytest.mark.unit
def test_amd_plus_minus_absolute() -> None:
    text = (
        "For the second quarter of 2026, AMD expects revenue to be approximately "
        "$11.2 billion, plus or minus $300 million."
    )
    claim = extract_guidance_from_text(
        text=text,
        meta_accession="0000002488-26-000072",
        meta_cik="0000002488",
        meta_ticker="AMD",
        meta_filing_date="2026-05-05",
        meta_accepted_at=datetime(2026, 5, 5, 16, 5, tzinfo=UTC),
        source_document="q12026991.htm",
    )
    assert claim is not None
    assert claim.target_fiscal_period.label == "FY2026Q2"
    assert claim.lower_bound_usd_m == pytest.approx(11200 - 300)
    assert claim.upper_bound_usd_m == pytest.approx(11200 + 300)
