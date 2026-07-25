"""OpenTelemetry span completeness and secret redaction."""

from __future__ import annotations

from pathlib import Path

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from guidance_watch.config import Settings
from guidance_watch.pipeline.analyze import analyze_accession
from guidance_watch.telemetry import REQUIRED_SPAN_NAMES, redact_value, setup_tracing

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
ACCESSION = "0000002488-24-000100"


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(
        GUIDANCE_WATCH_DB_PATH=tmp_path / "t.db",
        GUIDANCE_WATCH_CACHE_DIR=tmp_path / "cache",
        GUIDANCE_WATCH_REPORTS_DIR=tmp_path / "reports",
    )


@pytest.mark.unit
def test_analyze_emits_required_spans(settings: Settings) -> None:
    exporter = InMemorySpanExporter()
    setup_tracing(exporter=exporter, force=True)
    result = analyze_accession(ACCESSION, fixtures_root=FIXTURES, settings=settings)
    assert result.status == "completed"
    names = {s.name for s in exporter.get_finished_spans()}
    # poll is watch-path; analyze emits the rest for a successful run
    expected = set(REQUIRED_SPAN_NAMES) - {"poll"}
    missing = expected - names
    assert not missing, f"missing spans: {missing}; got {sorted(names)}"
    root = [s for s in exporter.get_finished_spans() if s.name == "analyze_filing"][0]
    assert root.attributes.get("filing.accession") == ACCESSION
    assert root.attributes.get("filing.ticker") == "AMD"


@pytest.mark.unit
def test_secret_values_redacted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-secret-value")
    assert redact_value("sk-test-secret-value") == "[REDACTED]"
    assert redact_value("Authorization: Bearer abc") == "[REDACTED]"
    assert redact_value("normal-attr") == "normal-attr"
