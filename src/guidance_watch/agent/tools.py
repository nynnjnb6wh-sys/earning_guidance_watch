"""Typed agent tools with temporal-safety guards."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from guidance_watch.agent.temporal import (
    TemporalLeakageError,
    ensure_not_after_cutoff,
    filter_history_before_cutoff,
)
from guidance_watch.analysis.scoring import calculate_assessment as _calculate_assessment
from guidance_watch.models import (
    AssessmentInput,
    FilingContent,
    FilingDocument,
    FilingMetadata,
    GuidanceClaim,
    HistoricalOutcome,
    ReliabilityAssessment,
    SentimentResult,
)


class FilingSource(Protocol):
    def get_filing_metadata(self, accession: str) -> FilingMetadata: ...

    def list_filing_documents(self, accession: str) -> list[FilingDocument]: ...

    def fetch_filing_document(self, accession: str, filename: str) -> FilingContent: ...


class HistorySource(Protocol):
    def get_company_history(self, cik: str, before: datetime) -> list[HistoricalOutcome]: ...


class SentimentSource(Protocol):
    def analyze_sentiment(self, text: str) -> SentimentResult: ...


@dataclass
class ToolContext:
    cutoff: datetime
    filing_source: FilingSource
    history_source: HistorySource
    sentiment_source: SentimentSource
    leakage_events: list[TemporalLeakageError] = field(default_factory=list)


@dataclass
class ToolResult:
    name: str
    ok: bool
    data: Any = None
    error: str | None = None


class AgentTools:
    """Six typed tools available to the LLM agent."""

    def __init__(self, ctx: ToolContext) -> None:
        self.ctx = ctx

    def get_filing_metadata(self, accession: str) -> ToolResult:
        meta = self.ctx.filing_source.get_filing_metadata(accession)
        try:
            ensure_not_after_cutoff(
                tool_name="get_filing_metadata",
                cutoff=self.ctx.cutoff,
                published=meta.accepted_at,
                detail=f"accession={accession}",
            )
        except TemporalLeakageError as exc:
            self.ctx.leakage_events.append(exc)
            return ToolResult(name="get_filing_metadata", ok=False, error=str(exc))
        return ToolResult(name="get_filing_metadata", ok=True, data=meta)

    def list_filing_documents(self, accession: str) -> ToolResult:
        docs = self.ctx.filing_source.list_filing_documents(accession)
        return ToolResult(name="list_filing_documents", ok=True, data=docs)

    def fetch_filing_document(self, accession: str, filename: str) -> ToolResult:
        content = self.ctx.filing_source.fetch_filing_document(accession, filename)
        # Document retrieval time is not a publication date; metadata cutoff already applied.
        return ToolResult(name="fetch_filing_document", ok=True, data=content)

    def get_company_history(self, cik: str, before: datetime | None = None) -> ToolResult:
        before = before or self.ctx.cutoff
        try:
            ensure_not_after_cutoff(
                tool_name="get_company_history",
                cutoff=self.ctx.cutoff,
                published=before,
                detail="before argument",
            )
        except TemporalLeakageError as exc:
            self.ctx.leakage_events.append(exc)
            return ToolResult(name="get_company_history", ok=False, error=str(exc))
        raw = self.ctx.history_source.get_company_history(cik, before)
        try:
            history = filter_history_before_cutoff(raw, self.ctx.cutoff)
        except TemporalLeakageError as exc:
            self.ctx.leakage_events.append(exc)
            return ToolResult(name="get_company_history", ok=False, error=str(exc))
        return ToolResult(name="get_company_history", ok=True, data=history)

    def analyze_sentiment(self, text: str) -> ToolResult:
        result = self.ctx.sentiment_source.analyze_sentiment(text)
        return ToolResult(name="analyze_sentiment", ok=True, data=result)

    def calculate_assessment(self, payload: AssessmentInput | dict[str, Any]) -> ToolResult:
        inp = AssessmentInput.model_validate(payload) if isinstance(payload, dict) else payload
        # Guard current claim accepted_at
        try:
            ensure_not_after_cutoff(
                tool_name="calculate_assessment",
                cutoff=self.ctx.cutoff,
                published=inp.current_claim.accepted_at,
                detail="current_claim.accepted_at",
            )
            filter_history_before_cutoff(list(inp.history), self.ctx.cutoff)
        except TemporalLeakageError as exc:
            self.ctx.leakage_events.append(exc)
            return ToolResult(name="calculate_assessment", ok=False, error=str(exc))
        assessment = _calculate_assessment(inp)
        return ToolResult(name="calculate_assessment", ok=True, data=assessment)


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_filing_metadata",
            "description": "Get metadata for a SEC filing accession.",
            "parameters": {
                "type": "object",
                "properties": {"accession": {"type": "string"}},
                "required": ["accession"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_filing_documents",
            "description": "List documents/attachments for a filing.",
            "parameters": {
                "type": "object",
                "properties": {"accession": {"type": "string"}},
                "required": ["accession"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_filing_document",
            "description": "Fetch and extract text for one filing document.",
            "parameters": {
                "type": "object",
                "properties": {
                    "accession": {"type": "string"},
                    "filename": {"type": "string"},
                },
                "required": ["accession", "filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_company_history",
            "description": "Load historical guidance outcomes on/before the cutoff.",
            "parameters": {
                "type": "object",
                "properties": {"cik": {"type": "string"}},
                "required": ["cik"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_sentiment",
            "description": "Run FinBERT (or fake) sentiment on outlook text.",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_assessment",
            "description": "Deterministically score historical reliability.",
            "parameters": {
                "type": "object",
                "properties": {"input": {"type": "object"}},
                "required": ["input"],
            },
        },
    },
]


def dispatch_tool(tools: AgentTools, name: str, arguments: dict[str, Any]) -> ToolResult:
    if name == "get_filing_metadata":
        return tools.get_filing_metadata(arguments["accession"])
    if name == "list_filing_documents":
        return tools.list_filing_documents(arguments["accession"])
    if name == "fetch_filing_document":
        return tools.fetch_filing_document(arguments["accession"], arguments["filename"])
    if name == "get_company_history":
        return tools.get_company_history(arguments["cik"])
    if name == "analyze_sentiment":
        return tools.analyze_sentiment(arguments["text"])
    if name == "calculate_assessment":
        return tools.calculate_assessment(arguments.get("input") or arguments)
    return ToolResult(name=name, ok=False, error=f"unknown tool: {name}")


# Re-export models used by callers
__all__ = [
    "AgentTools",
    "FilingSource",
    "HistorySource",
    "SentimentSource",
    "TOOL_SCHEMAS",
    "ToolContext",
    "ToolResult",
    "dispatch_tool",
    "GuidanceClaim",
    "ReliabilityAssessment",
]
