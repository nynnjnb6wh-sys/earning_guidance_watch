"""Backfill over fixture filings + curated actuals seed."""

from __future__ import annotations

from pathlib import Path

import pytest

from guidance_watch.config import Settings
from guidance_watch.persistence.db import connect
from guidance_watch.pipeline.backfill import run_backfill

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
ACTUALS = Path(__file__).resolve().parents[2] / "seed" / "actuals.csv"


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(
        GUIDANCE_WATCH_DB_PATH=tmp_path / "t.db",
        GUIDANCE_WATCH_CACHE_DIR=tmp_path / "cache",
        GUIDANCE_WATCH_REPORTS_DIR=tmp_path / "reports",
        OPENROUTER_API_KEY="",
    )


@pytest.mark.integration
def test_backfill_amd_links_fixture_claim(settings: Settings) -> None:
    result = run_backfill(
        ticker="AMD",
        quarters=8,
        fixtures_root=FIXTURES,
        actuals_csv=ACTUALS,
        settings=settings,
    )
    assert result.accessions_seen >= 1
    assert result.claims_extracted >= 1
    # Fixture extracts FY2024Q1; seed has FY2024Q1 actual for AMD
    assert result.outcomes_linked >= 1

    conn = connect(settings.db_path)
    try:
        row = conn.execute("SELECT COUNT(*) AS n FROM guidance_outcomes").fetchone()
        assert int(row["n"]) >= 1
        outcome = conn.execute(
            "SELECT original_lower_usd_m, actual_revenue_usd_m FROM guidance_outcomes"
        ).fetchone()
        assert float(outcome["original_lower_usd_m"]) == 5400.0
        assert float(outcome["actual_revenue_usd_m"]) == 5470.0
    finally:
        conn.close()
