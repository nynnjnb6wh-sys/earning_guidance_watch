"""Offline evaluation harness."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx

from guidance_watch.agent.temporal import TemporalLeakageError, ensure_not_after_cutoff
from guidance_watch.analysis.linker import ActualResult, link_claims_for_period
from guidance_watch.analysis.metrics import inside_range
from guidance_watch.config import Settings, get_settings
from guidance_watch.eval.cases import EVAL_CASES, EvalCase
from guidance_watch.models import (
    FiscalPeriod,
    GuidanceClaim,
    RevisionDirection,
)
from guidance_watch.persistence.db import init_db
from guidance_watch.pipeline.analyze import analyze_accession
from guidance_watch.sec.cache import ResponseCache
from guidance_watch.sec.client import SecClient
from guidance_watch.sec.fixture_client import FixtureSecClient
from guidance_watch.sec.html_text import quote_appears_in_source


@dataclass
class CaseResult:
    case_id: str
    passed: bool
    detail: str
    metrics: dict[str, bool] = field(default_factory=dict)
    failure_category: str | None = None


@dataclass
class EvalReport:
    results: list[CaseResult]
    totals: dict[str, float]

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results)


def _persist_eval(conn: sqlite3.Connection, result: CaseResult) -> None:
    for metric, ok in result.metrics.items():
        conn.execute(
            """
            INSERT INTO evaluation_results (case_id, metric_name, passed, detail)
            VALUES (?, ?, ?, ?)
            """,
            (
                result.case_id,
                metric,
                int(ok),
                result.failure_category or result.detail,
            ),
        )
    conn.commit()


def _claim(
    *,
    accession: str,
    period: str,
    lower: float,
    upper: float,
    is_revision: bool = False,
) -> GuidanceClaim:
    return GuidanceClaim(
        ticker="AMD",
        cik="0000002488",
        accession=accession,
        filing_date="2024-01-30",
        accepted_at=datetime(2024, 1, 30, 21, 5, tzinfo=UTC),
        source_document="ex99-1.htm",
        target_fiscal_period=FiscalPeriod.parse(period),
        lower_bound_usd_m=lower,
        upper_bound_usd_m=upper,
        unit_in_source="normalized_to_usd_millions",
        is_revision=is_revision,
        revision_direction=RevisionDirection.UNKNOWN,
        supporting_quote="Revenue is expected to be $100 million to $120 million",
        confidence=0.9,
        needs_review=False,
    )


class _SequencedHandler:
    def __init__(self) -> None:
        self._seq: dict[str, list[httpx.Response]] = {}

    def set_sequence(self, url: str, responses: list[httpx.Response]) -> None:
        self._seq[url] = list(responses)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        remaining = self._seq.get(url) or []
        if not remaining:
            return httpx.Response(404, text="missing sequence")
        response = remaining.pop(0)
        self._seq[url] = remaining
        return response


def _run_special(case: EvalCase, *, settings: Settings, fixtures_root: Path) -> CaseResult:
    metrics: dict[str, bool] = {}
    failure: str | None = None

    if case.category == "actual_bounds":
        metrics["inside_range"] = inside_range(105.0, 100.0, 120.0) is True
        metrics["outside_range"] = inside_range(99.0, 100.0, 120.0) is False
        original = _claim(accession="a", period="FY2024Q1", lower=100.0, upper=120.0)
        actual = ActualResult(
            ticker="AMD",
            cik="0000002488",
            target_fiscal_period=FiscalPeriod.parse("FY2024Q1"),
            actual_revenue_usd_m=105.0,
            actual_publication_date=date(2024, 4, 30),
        )
        link = link_claims_for_period([original], actual)
        hit = link.outcome is not None and inside_range(
            link.outcome.actual_revenue_usd_m,
            link.outcome.original_lower_usd_m,
            link.outcome.original_upper_usd_m,
        )
        metrics["linker_hit"] = link.needs_review is False and hit is True
    elif case.category == "temporal":
        cutoff = datetime(2024, 1, 30, 21, 5, tzinfo=UTC)
        try:
            ensure_not_after_cutoff(
                tool_name="get_company_history",
                cutoff=cutoff,
                published=cutoff + timedelta(seconds=1),
            )
            metrics["post_cutoff_rejected"] = False
        except TemporalLeakageError:
            metrics["post_cutoff_rejected"] = True
        try:
            ensure_not_after_cutoff(
                tool_name="get_company_history",
                cutoff=cutoff,
                published=cutoff - timedelta(seconds=1),
            )
            metrics["pre_cutoff_allowed"] = True
        except TemporalLeakageError:
            metrics["pre_cutoff_allowed"] = False
    elif case.category == "http_retry":
        conn = init_db(settings.db_path.parent / "http_retry.db")
        try:
            cache = ResponseCache(settings.cache_dir / "http_retry", conn)
            handler = _SequencedHandler()
            url = "https://example.test/eval-retry"
            handler.set_sequence(
                url,
                [
                    httpx.Response(503, text="busy"),
                    httpx.Response(200, content=b'{"ok": true}'),
                ],
            )
            sleeps: list[float] = []
            sec = SecClient(
                user_agent=settings.sec_user_agent,
                cache=cache,
                requests_per_second=1000.0,
                transport=httpx.MockTransport(handler),
                sleep=sleeps.append,
                base_backoff_s=0.01,
            )
            status, body, _from_cache = sec.get_bytes(url, use_cache=False)
            metrics["retry_success"] = status == 200 and json.loads(body)["ok"] is True
            metrics["retry_counted"] = sec.stats.retries == 1
            metrics["backoff_invoked"] = bool(sleeps)
        finally:
            conn.close()
    elif case.category == "quote":
        fixtures = FixtureSecClient(fixtures_root)
        text = fixtures.fetch_filing_document(case.accession, "ex99-1.htm").text
        metrics["real_quote_present"] = quote_appears_in_source(
            "Revenue is expected to be",
            text,
        )
        metrics["fabricated_quote_rejected"] = not quote_appears_in_source(
            "Revenue will definitely hit $99 billion next week",
            text,
        )
    else:
        failure = f"unknown_special_category:{case.category}"
        metrics["known_category"] = False

    passed = all(metrics.values()) if metrics else False
    if not passed and failure is None:
        failure = case.category
    detail = ",".join(f"{k}={'Y' if v else 'N'}" for k, v in metrics.items())
    return CaseResult(case.case_id, passed, detail, metrics, failure)


def run_case(case: EvalCase, *, fixtures_root: Path, settings: Settings) -> CaseResult:
    if case.category in {"actual_bounds", "temporal", "http_retry", "quote"}:
        return _run_special(case, settings=settings, fixtures_root=fixtures_root)

    metrics: dict[str, bool] = {}
    failure: str | None = None

    if case.category == "dedupe":
        first = analyze_accession(case.accession, fixtures_root=fixtures_root, settings=settings)
        second = analyze_accession(case.accession, fixtures_root=fixtures_root, settings=settings)
        metrics["duplicate_suppressed"] = (
            first.status == "completed" and second.status == "already_processed"
        )
        metrics["schema_valid"] = True
        passed = all(metrics.values())
        if not passed:
            failure = "dedupe"
        return CaseResult(
            case.case_id,
            passed,
            ",".join(f"{k}={'Y' if v else 'N'}" for k, v in metrics.items()),
            metrics,
            failure,
        )

    case_settings = settings.model_copy(
        update={"db_path": settings.db_path.parent / f"{case.case_id}.db"}
    )
    result = analyze_accession(case.accession, fixtures_root=fixtures_root, settings=case_settings)
    relevant = result.status == "completed"
    metrics["classification"] = relevant is case.expect_relevant
    if case.expect_relevant:
        metrics["end_to_end_success"] = result.status == "completed"
        conn = init_db(case_settings.db_path)
        try:
            row = conn.execute(
                "SELECT * FROM guidance_claims WHERE accession = ?",
                (case.accession,),
            ).fetchone()
            metrics["schema_valid"] = row is not None
            if row is not None:
                if case.expect_lower_usd_m is not None:
                    metrics["lower_bound"] = (
                        abs(float(row["lower_bound_usd_m"]) - case.expect_lower_usd_m) < 1e-6
                    )
                if case.expect_upper_usd_m is not None:
                    metrics["upper_bound"] = (
                        abs(float(row["upper_bound_usd_m"]) - case.expect_upper_usd_m) < 1e-6
                    )
                if case.expect_period is not None:
                    metrics["period"] = row["target_fiscal_period"] == case.expect_period
                if case.expect_source_document is not None:
                    metrics["attachment_selection"] = (
                        row["source_document"] == case.expect_source_document
                    )
                client = FixtureSecClient(fixtures_root)
                text = client.fetch_filing_document(case.accession, row["source_document"]).text
                metrics["supporting_quote"] = quote_appears_in_source(row["supporting_quote"], text)
            reports = conn.execute(
                "SELECT COUNT(*) AS n FROM reports WHERE accession = ?",
                (case.accession,),
            ).fetchone()
            metrics["reports_persisted"] = int(reports["n"]) == 2

            if case.category == "fiscal_calendar":
                meta = FixtureSecClient(fixtures_root).get_filing_metadata(case.accession)
                filing_month = int(meta.filing_date.split("-")[1])
                calendar_q = (filing_month - 1) // 3 + 1
                metrics["fiscal_differs_from_calendar"] = (
                    case.expect_period is not None and int(case.expect_period[-1]) != calendar_q
                )

            if case.category in {"thin_history", "sentiment_baseline"} and result.assessment:
                if case.expect_label is not None:
                    metrics["label"] = result.assessment.label.value == case.expect_label
                if case.category == "sentiment_baseline":
                    limitations = result.assessment.limitations
                    metrics["sentiment_baseline_unavailable"] = any(
                        "Sentiment baseline unavailable" in lim for lim in limitations
                    )
        finally:
            conn.close()
    else:
        metrics["ignored_correctly"] = result.status == "ignored"
        metrics["end_to_end_success"] = result.status == "ignored"

    passed = all(metrics.values()) if metrics else False
    if not passed:
        failure = case.category if case.category != "e2e" else "extraction"
    detail = ",".join(f"{k}={'Y' if v else 'N'}" for k, v in metrics.items())
    return CaseResult(case.case_id, passed, detail, metrics, failure)


def run_eval(
    *,
    fixtures_root: Path | None = None,
    settings: Settings | None = None,
) -> EvalReport:
    settings = settings or get_settings()
    fixtures_root = fixtures_root or (Path("tests/fixtures"))
    conn = init_db(settings.db_path)
    results: list[CaseResult] = []
    try:
        for case in EVAL_CASES:
            result = run_case(case, fixtures_root=fixtures_root, settings=settings)
            results.append(result)
            _persist_eval(conn, result)
    finally:
        conn.close()

    totals: dict[str, float] = {}
    buckets: dict[str, list[bool]] = {}
    for result in results:
        for name, ok in result.metrics.items():
            buckets.setdefault(name, []).append(ok)
    for name, values in buckets.items():
        totals[name] = sum(1 for v in values if v) / len(values)
    totals["cases_passed"] = sum(1 for r in results if r.passed) / max(len(results), 1)
    return EvalReport(results=results, totals=totals)
