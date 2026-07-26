"""Offline evaluation harness smoke test."""

from __future__ import annotations

from pathlib import Path

import pytest

from guidance_watch.config import Settings
from guidance_watch.eval.harness import run_eval

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.mark.eval
def test_eval_harness_passes_offline(tmp_path: Path) -> None:
    settings = Settings(
        GUIDANCE_WATCH_DB_PATH=tmp_path / "eval.db",
        GUIDANCE_WATCH_CACHE_DIR=tmp_path / "cache",
        GUIDANCE_WATCH_REPORTS_DIR=tmp_path / "reports",
        OPENROUTER_API_KEY="",
    )
    report = run_eval(fixtures_root=FIXTURES, settings=settings)
    assert report.passed, {r.case_id: r.detail for r in report.results if not r.passed}
    assert report.totals["cases_passed"] == 1.0
