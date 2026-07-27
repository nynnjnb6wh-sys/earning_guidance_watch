"""Analyze loads linked outcomes via SqliteHistorySource / AgentTools."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from guidance_watch.config import Settings
from guidance_watch.models import (
    FilingMetadata,
    FiscalPeriod,
    GuidanceClaim,
    HistoricalOutcome,
    RevisionDirection,
)
from guidance_watch.persistence import repository as repo
from guidance_watch.persistence.db import init_db
from guidance_watch.persistence.outcomes import SqliteHistorySource, upsert_outcome
from guidance_watch.pipeline.analyze import analyze_accession

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
ACCESSION = "0000002488-24-000500"


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(
        GUIDANCE_WATCH_DB_PATH=tmp_path / "hist.db",
        GUIDANCE_WATCH_CACHE_DIR=tmp_path / "cache",
        GUIDANCE_WATCH_REPORTS_DIR=tmp_path / "reports",
        OPENROUTER_API_KEY="",
    )


def _seed_history(settings: Settings, *, n: int = 4) -> None:
    conn = init_db(settings.db_path)
    try:
        repo.ensure_company(conn, cik="0000002488", ticker="AMD", name="AMD")
        for i in range(n):
            accession = f"0000002488-23-00010{i}"
            repo.upsert_filing(
                conn,
                FilingMetadata(
                    accession=accession,
                    cik="0000002488",
                    ticker="AMD",
                    form="8-K",
                    filing_date="2023-01-01",
                    accepted_at=datetime(2023, 1, 1, tzinfo=UTC),
                    primary_document="ex99-1.htm",
                    items=["2.02"],
                ),
            )
            claim = GuidanceClaim(
                ticker="AMD",
                cik="0000002488",
                accession=accession,
                filing_date="2023-01-01",
                accepted_at=datetime(2023, 1, 1, tzinfo=UTC),
                source_document="ex99-1.htm",
                target_fiscal_period=FiscalPeriod.parse(f"FY2023Q{i + 1}"),
                lower_bound_usd_m=1000.0 + i,
                upper_bound_usd_m=1100.0 + i,
                unit_in_source="millions",
                is_revision=False,
                revision_direction=RevisionDirection.UNKNOWN,
                supporting_quote="seed",
                confidence=0.9,
                needs_review=False,
            )
            claim_id = repo.insert_guidance_claim(conn, claim)
            upsert_outcome(
                conn,
                HistoricalOutcome(
                    guidance_claim_id=claim_id,
                    target_fiscal_period=claim.target_fiscal_period,
                    original_lower_usd_m=claim.lower_bound_usd_m,
                    original_upper_usd_m=claim.upper_bound_usd_m,
                    latest_lower_usd_m=claim.lower_bound_usd_m,
                    latest_upper_usd_m=claim.upper_bound_usd_m,
                    actual_revenue_usd_m=1050.0 + i,
                    actual_publication_date=date(2023, 4 + i, 15),
                    revision_count=0,
                    downward_revision_occurred=False,
                    source_documents=["ex99-1.htm"],
                ),
            )
        conn.commit()
    finally:
        conn.close()


@pytest.mark.integration
def test_sqlite_history_source_respects_cutoff(settings: Settings) -> None:
    _seed_history(settings, n=2)
    conn = init_db(settings.db_path)
    try:
        source = SqliteHistorySource(conn)
        before = datetime(2023, 5, 1, tzinfo=UTC)
        history = source.get_company_history("0000002488", before)
        assert len(history) == 1
        assert history[0].target_fiscal_period.label == "FY2023Q1"
    finally:
        conn.close()


@pytest.mark.integration
def test_analyze_uses_db_history_for_assessment(settings: Settings) -> None:
    _seed_history(settings, n=4)
    result = analyze_accession(ACCESSION, fixtures_root=FIXTURES, settings=settings)
    assert result.status == "completed"
    assert result.assessment is not None
    assert result.assessment.usable_quarters == 4
    # Historical tone baseline is still empty → unavailable (not insufficient_history).
    assert result.assessment.label.value == "unavailable"
