"""Analyze a single accession end-to-end (fixture-friendly vertical slice)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from guidance_watch import AGENT_VERSION, PROMPT_VERSION, SCORING_VERSION
from guidance_watch.agent.provider import llm_mode, resolve_provider
from guidance_watch.agent.tools import AgentTools, ToolContext
from guidance_watch.config import Settings, get_settings
from guidance_watch.models import (
    AssessmentInput,
    GuidanceClaim,
    ReliabilityAssessment,
)
from guidance_watch.persistence import repository as repo
from guidance_watch.persistence.db import init_db
from guidance_watch.persistence.outcomes import SqliteHistorySource
from guidance_watch.pipeline.extract import (
    extract_guidance_from_text,
    rank_exhibit_candidates,
    select_exhibit99,
)
from guidance_watch.reporting.render import render_json_report, render_markdown_report
from guidance_watch.sec.fixture_client import FixtureSecClient
from guidance_watch.sentiment import FakeSentimentProvider
from guidance_watch.telemetry import filing_trace, setup_tracing, span
from guidance_watch.telemetry.setup import set_attrs

# Re-export extract helpers for callers that imported them from this module.
__all__ = [
    "AnalyzeResult",
    "analyze_accession",
    "extract_guidance_from_text",
    "rank_exhibit_candidates",
    "select_exhibit99",
]


@dataclass
class AnalyzeResult:
    status: str
    accession: str
    run_id: str | None = None
    detail: str | None = None
    assessment: ReliabilityAssessment | None = None


def analyze_accession(
    accession: str,
    *,
    fixtures_root: Path,
    settings: Settings | None = None,
) -> AnalyzeResult:
    settings = settings or get_settings()
    setup_tracing()
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
        sentiment_source = FakeSentimentProvider(model_revision="slice2")
        history_source = SqliteHistorySource(conn)
        with filing_trace(accession=accession) as root_span:
            with span("retrieve metadata", accession=accession):
                meta = client.get_filing_metadata(accession)
            set_attrs(
                root_span,
                {
                    "filing.ticker": meta.ticker,
                    "filing.cik": meta.cik,
                    "filing.cutoff": meta.accepted_at.isoformat(),
                },
            )
            tools = AgentTools(
                ToolContext(
                    cutoff=meta.accepted_at,
                    filing_source=client,
                    history_source=history_source,
                    sentiment_source=sentiment_source,
                )
            )
            with span("detect", form=meta.form):
                repo.upsert_filing(conn, meta)
                repo.insert_job_attempt(conn, accession=accession, status="running")
            with span("filter", items=",".join(meta.items)):
                documents = client.list_filing_documents(accession)
                candidates = rank_exhibit_candidates(documents)
            if not candidates:
                with span("persist result", status="ignored"):
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

            claim: GuidanceClaim | None = None
            model_identifier = "deterministic-extractor-v1"
            # Live OpenRouter extraction is opt-in even when a key is present.
            # History/scoring always go through AgentTools + SqliteHistorySource.
            use_live_agent = (
                llm_mode(settings) == "live"
                and (os.environ.get("GUIDANCE_WATCH_USE_LIVE_AGENT") or "")
                .strip()
                .lower()
                in {"1", "true", "yes"}
            )

            if use_live_agent:
                with span("extract guidance", mode="live"):
                    from guidance_watch.agent.runner import run_agent

                    try:
                        provider = resolve_provider(settings, require_live=True)
                        agent_result = run_agent(
                            accession=accession, tools=tools, provider=provider
                        )
                        model_identifier = (
                            agent_result.model_id or settings.openrouter_model
                        )
                        if agent_result.relevant and agent_result.claim is not None:
                            claim = agent_result.claim
                        # If the live agent declines or fails to produce a claim,
                        # fall through to the deterministic extractor below.
                    except Exception as exc:  # noqa: BLE001 — fall back offline
                        set_attrs(root_span, {"agent.live_error": str(exc)[:200]})

            if claim is None:
                for filename in candidates:
                    with span("retrieve document", filename=filename):
                        content = client.fetch_filing_document(accession, filename)
                    with span("classify", filename=filename):
                        claim = extract_guidance_from_text(
                            text=content.text,
                            meta_accession=meta.accession,
                            meta_cik=meta.cik,
                            meta_ticker=meta.ticker or "UNKNOWN",
                            meta_filing_date=meta.filing_date,
                            meta_accepted_at=meta.accepted_at,
                            source_document=filename,
                        )
                    if claim is not None:
                        break
            if claim is None:
                with span("persist result", status="ignored"):
                    run_id = repo.insert_analysis_run(
                        conn,
                        accession=accession,
                        ticker=meta.ticker,
                        cik=meta.cik,
                        status="ignored",
                        prompt_version=PROMPT_VERSION,
                        agent_version=AGENT_VERSION,
                        scoring_version=SCORING_VERSION,
                        model_identifier=model_identifier,
                        assessment=None,
                        ignore_reason="no_quarterly_gaap_revenue_guidance",
                    )
                    conn.commit()
                return AnalyzeResult(status="ignored", accession=accession, run_id=run_id)

            if not use_live_agent:
                with span("extract guidance", period=claim.target_fiscal_period.label):
                    pass  # claim already extracted; span records presence

            with span("load history") as hist_span:
                hist_result = tools.get_company_history(claim.cik)
                history = list(hist_result.data or []) if hist_result.ok else []
                set_attrs(hist_span, {"usable_quarters": len(history)})
            with span("sentiment inference", model_name=sentiment_source.model_name):
                source_text = client.fetch_filing_document(
                    accession, claim.source_document
                ).text
                sent_result = tools.analyze_sentiment(source_text)
                sentiment = sent_result.data if sent_result.ok else None
            with span("calculate assessment"):
                assess_result = tools.calculate_assessment(
                    AssessmentInput(
                        current_claim=claim,
                        history=history,
                        current_sentiment=sentiment,
                        historical_tone_scores=[],
                    )
                )
                if not assess_result.ok or assess_result.data is None:
                    raise RuntimeError(
                        assess_result.error or "calculate_assessment failed"
                    )
                assessment = assess_result.data

            with span("render report"):
                json_body = render_json_report(claim, assessment)
                md_body = render_markdown_report(claim, assessment)
                reports_dir = settings.reports_dir / (meta.ticker or "UNKNOWN") / accession
                reports_dir.mkdir(parents=True, exist_ok=True)
                json_path = reports_dir / "report.json"
                md_path = reports_dir / "report.md"
                json_path.write_text(json_body, encoding="utf-8")
                md_path.write_text(md_body, encoding="utf-8")

            with span("persist result", status="completed"):
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
                    model_identifier=model_identifier,
                    assessment=assessment,
                )
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
            set_attrs(root_span, {"job.status": "completed"})
            return AnalyzeResult(
                status="completed",
                accession=accession,
                run_id=run_id,
                assessment=assessment,
            )
    finally:
        conn.close()
