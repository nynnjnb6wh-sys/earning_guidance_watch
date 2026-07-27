"""Slice 2 vertical slice: fixture filing → persisted reports + dedupe."""

from __future__ import annotations

from pathlib import Path

import pytest

from guidance_watch.config import Settings
from guidance_watch.persistence import repository as repo
from guidance_watch.persistence.db import connect
from guidance_watch.pipeline.analyze import analyze_accession

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
ACCESSION = "0000002488-24-000100"


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(
        GUIDANCE_WATCH_DB_PATH=tmp_path / "test.db",
        GUIDANCE_WATCH_CACHE_DIR=tmp_path / "cache",
        GUIDANCE_WATCH_REPORTS_DIR=tmp_path / "reports",
        OPENROUTER_API_KEY="",
    )


@pytest.mark.integration
def test_analyze_case1_persists_claim_and_reports(settings: Settings) -> None:
    result = analyze_accession(ACCESSION, fixtures_root=FIXTURES, settings=settings)
    assert result.status == "completed"
    assert result.run_id is not None
    assert result.assessment is not None
    assert result.assessment.label.value == "insufficient_history"

    conn = connect(settings.db_path)
    try:
        assert repo.count_guidance_claims(conn, ACCESSION) == 1
        reports = repo.load_reports(conn, ACCESSION)
        formats = {r["format"] for r in reports}
        assert formats == {"json", "markdown"}
        run = repo.get_analysis_run(conn, ACCESSION)
        assert run is not None
        assert run["status"] == "completed"
        assert run["prompt_version"]
        assert run["agent_version"]
        assert run["scoring_version"]
    finally:
        conn.close()

    json_path = settings.reports_dir / "AMD" / ACCESSION / "report.json"
    md_path = settings.reports_dir / "AMD" / ACCESSION / "report.md"
    assert json_path.is_file()
    assert md_path.is_file()
    body = json_path.read_text()
    assert "5.4" in body or "5400" in body
    assert "supporting_quote" in body


@pytest.mark.integration
def test_duplicate_accession_not_reprocessed(settings: Settings) -> None:
    first = analyze_accession(ACCESSION, fixtures_root=FIXTURES, settings=settings)
    second = analyze_accession(ACCESSION, fixtures_root=FIXTURES, settings=settings)
    assert first.status == "completed"
    assert second.status == "already_processed"
    assert second.run_id == first.run_id

    conn = connect(settings.db_path)
    try:
        assert repo.count_guidance_claims(conn, ACCESSION) == 1
        runs = conn.execute("SELECT COUNT(*) AS n FROM analysis_runs").fetchone()
        assert int(runs["n"]) == 1
    finally:
        conn.close()
