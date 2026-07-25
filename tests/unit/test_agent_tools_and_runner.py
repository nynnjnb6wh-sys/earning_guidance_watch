"""Slice 4: tool temporal guard + scripted agent runner."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from guidance_watch.agent.provider import AssistantMessage, ScriptedProvider, ToolCall
from guidance_watch.agent.runner import run_agent
from guidance_watch.agent.temporal import TemporalLeakageError, ensure_not_after_cutoff
from guidance_watch.agent.tools import AgentTools, ToolContext
from guidance_watch.models import (
    FiscalPeriod,
    HistoricalOutcome,
    SentimentResult,
)
from guidance_watch.sec.fixture_client import FixtureSecClient
from guidance_watch.sec.html_text import quote_appears_in_source

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
ACCESSION = "0000002488-24-000100"


class EmptyHistory:
    def get_company_history(self, cik: str, before: datetime) -> list[HistoricalOutcome]:
        return []


class FakeSentiment:
    def analyze_sentiment(self, text: str) -> SentimentResult:
        return SentimentResult.from_probabilities(
            model_name="fake",
            model_revision="test",
            positive_probability=0.4,
            neutral_probability=0.4,
            negative_probability=0.2,
            analyzed_text_hash="x",
        )


class PostCutoffHistory:
    def get_company_history(self, cik: str, before: datetime) -> list[HistoricalOutcome]:
        return [
            HistoricalOutcome(
                guidance_claim_id="future",
                target_fiscal_period=FiscalPeriod.parse("FY2024Q2"),
                original_lower_usd_m=100,
                original_upper_usd_m=110,
                latest_lower_usd_m=100,
                latest_upper_usd_m=110,
                actual_revenue_usd_m=105,
                actual_publication_date=date(2099, 1, 1),
                revision_count=0,
                downward_revision_occurred=False,
                source_documents=[],
            )
        ]


def _tools(
    *,
    cutoff: datetime | None = None,
    history: object | None = None,
) -> AgentTools:
    client = FixtureSecClient(FIXTURES)
    meta = client.get_filing_metadata(ACCESSION)
    ctx = ToolContext(
        cutoff=cutoff or meta.accepted_at,
        filing_source=client,
        history_source=history or EmptyHistory(),  # type: ignore[arg-type]
        sentiment_source=FakeSentiment(),
    )
    return AgentTools(ctx)


@pytest.mark.unit
def test_quote_must_appear_in_source() -> None:
    client = FixtureSecClient(FIXTURES)
    text = client.fetch_filing_document(ACCESSION, "ex99-1.htm").text
    assert quote_appears_in_source("Revenue is expected to be $5.4 billion to $6.0 billion", text)
    assert not quote_appears_in_source("Revenue will be $99 billion", text)


@pytest.mark.unit
def test_post_cutoff_history_rejected() -> None:
    tools = _tools(history=PostCutoffHistory())
    result = tools.get_company_history("0000002488")
    assert result.ok is False
    assert "temporal leakage" in (result.error or "")
    assert tools.ctx.leakage_events


@pytest.mark.unit
def test_cutoff_guard_on_datetime() -> None:
    cutoff = datetime(2024, 1, 30, 21, 5, tzinfo=UTC)
    with pytest.raises(TemporalLeakageError):
        ensure_not_after_cutoff(
            tool_name="test",
            cutoff=cutoff,
            published=cutoff + timedelta(seconds=1),
        )


@pytest.mark.unit
def test_scripted_agent_selects_exhibit_and_extracts() -> None:
    tools = _tools()
    script = [
        AssistantMessage(
            tool_calls=[
                ToolCall(id="1", name="get_filing_metadata", arguments={"accession": ACCESSION})
            ]
        ),
        AssistantMessage(
            tool_calls=[
                ToolCall(id="2", name="list_filing_documents", arguments={"accession": ACCESSION})
            ]
        ),
        AssistantMessage(
            tool_calls=[
                ToolCall(
                    id="3",
                    name="fetch_filing_document",
                    arguments={"accession": ACCESSION, "filename": "ex99-1.htm"},
                )
            ]
        ),
        AssistantMessage(
            content=json.dumps(
                {
                    "relevant": True,
                    "ticker": "AMD",
                    "cik": "0000002488",
                    "accession": ACCESSION,
                    "filing_date": "2024-01-30",
                    "accepted_at": "2024-01-30T21:05:12+00:00",
                    "source_document": "ex99-1.htm",
                    "target_fiscal_period": {
                        "label": "FY2024Q1",
                        "fiscal_year": 2024,
                        "fiscal_quarter": 1,
                    },
                    "metric": "revenue",
                    "gaap_or_non_gaap": "gaap",
                    "lower_bound_usd_m": 5400.0,
                    "upper_bound_usd_m": 6000.0,
                    "currency": "USD",
                    "unit_in_source": "billions",
                    "is_revision": False,
                    "revision_direction": "unknown",
                    "supporting_quote": "Revenue is expected to be $5.4 billion to $6.0 billion",
                    "confidence": 0.9,
                    "needs_review": False,
                }
            )
        ),
    ]
    result = run_agent(
        accession=ACCESSION,
        tools=tools,
        provider=ScriptedProvider(script),
    )
    assert result.relevant is True
    assert result.claim is not None
    assert result.claim.lower_bound_usd_m == 5400.0
    assert "get_filing_metadata" in result.tool_calls
    assert "fetch_filing_document" in result.tool_calls


@pytest.mark.unit
def test_scripted_agent_irrelevant_filing() -> None:
    tools = _tools()
    script = [
        AssistantMessage(
            tool_calls=[
                ToolCall(id="1", name="list_filing_documents", arguments={"accession": ACCESSION})
            ]
        ),
        AssistantMessage(
            content=json.dumps({"relevant": False, "reason": "no_quarterly_gaap_revenue_guidance"})
        ),
    ]
    result = run_agent(accession=ACCESSION, tools=tools, provider=ScriptedProvider(script))
    assert result.relevant is False
    assert result.reason == "no_quarterly_gaap_revenue_guidance"


@pytest.mark.unit
def test_hallucinated_quote_rejected() -> None:
    tools = _tools()
    script = [
        AssistantMessage(
            content=json.dumps(
                {
                    "relevant": True,
                    "ticker": "AMD",
                    "cik": "0000002488",
                    "accession": ACCESSION,
                    "filing_date": "2024-01-30",
                    "accepted_at": "2024-01-30T21:05:12+00:00",
                    "source_document": "ex99-1.htm",
                    "target_fiscal_period": {
                        "label": "FY2024Q1",
                        "fiscal_year": 2024,
                        "fiscal_quarter": 1,
                    },
                    "metric": "revenue",
                    "gaap_or_non_gaap": "gaap",
                    "lower_bound_usd_m": 5400.0,
                    "upper_bound_usd_m": 6000.0,
                    "currency": "USD",
                    "unit_in_source": "billions",
                    "is_revision": False,
                    "revision_direction": "unknown",
                    "supporting_quote": "Revenue will definitely be $99 billion next quarter",
                    "confidence": 0.9,
                    "needs_review": False,
                }
            )
        )
    ]
    result = run_agent(accession=ACCESSION, tools=tools, provider=ScriptedProvider(script))
    # Hallucinated quote fails validation; may fall back to deterministic extract
    # which succeeds on the same fixture — that is acceptable. Force pure reject by
    # checking quote path: if claim exists, quote must appear in source.
    if result.claim is not None:
        text = FixtureSecClient(FIXTURES).fetch_filing_document(ACCESSION, "ex99-1.htm").text
        assert quote_appears_in_source(result.claim.supporting_quote, text)
        assert "99 billion" not in result.claim.supporting_quote
    else:
        assert result.relevant is False
