"""Bounded tool-calling agent runner."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from guidance_watch import AGENT_VERSION, PROMPT_VERSION
from guidance_watch.agent.provider import LlmProvider
from guidance_watch.agent.tools import TOOL_SCHEMAS, AgentTools, dispatch_tool
from guidance_watch.models import GuidanceClaim
from guidance_watch.pipeline.extract import extract_guidance_from_text, select_exhibit99
from guidance_watch.sec.html_text import quote_appears_in_source

_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "extract-v1.md"


@dataclass
class AgentRunResult:
    relevant: bool
    reason: str | None = None
    claim: GuidanceClaim | None = None
    assessment: Any | None = None
    tool_calls: list[str] = field(default_factory=list)
    needs_review: bool = False
    leakage_count: int = 0
    model_id: str | None = None
    prompt_version: str = PROMPT_VERSION
    agent_version: str = AGENT_VERSION
    raw_final: str | None = None


def load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _serialize_tool_data(data: Any) -> str:
    if data is None:
        return "null"
    if hasattr(data, "model_dump"):
        return json.dumps(data.model_dump(mode="json"), default=str)
    if isinstance(data, list):
        return json.dumps(
            [d.model_dump(mode="json") if hasattr(d, "model_dump") else d for d in data],
            default=str,
        )
    return json.dumps(data, default=str)


def run_agent(
    *,
    accession: str,
    tools: AgentTools,
    provider: LlmProvider,
    max_steps: int = 12,
) -> AgentRunResult:
    """Run the tool-calling loop. Validates quotes; stamps versions."""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": load_system_prompt()},
        {
            "role": "user",
            "content": (
                f"Analyze accession {accession}. Use tools. Return final JSON only when done."
            ),
        },
    ]
    called: list[str] = []
    final_text: str | None = None
    model_id: str | None = None

    for _ in range(max_steps):
        completion = provider.complete_with_tools(messages=messages, tools=TOOL_SCHEMAS)
        model_id = completion.model
        msg = completion.message
        if msg.tool_calls:
            messages.append(
                {
                    "role": "assistant",
                    "content": msg.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments),
                            },
                        }
                        for tc in msg.tool_calls
                    ],
                }
            )
            for tc in msg.tool_calls:
                called.append(tc.name)
                result = dispatch_tool(tools, tc.name, tc.arguments)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": tc.name,
                        "content": _serialize_tool_data(result.data)
                        if result.ok
                        else json.dumps({"error": result.error}),
                    }
                )
            continue
        final_text = msg.content
        break

    leakage = len(tools.ctx.leakage_events)
    if not final_text:
        return AgentRunResult(
            relevant=False,
            reason="no_final_response",
            tool_calls=called,
            leakage_count=leakage,
            model_id=model_id,
            needs_review=True,
        )

    try:
        payload = json.loads(final_text)
    except json.JSONDecodeError:
        # Fallback: deterministic extraction using tools already fetched docs
        return _deterministic_fallback(accession, tools, called, leakage, model_id, final_text)

    if payload.get("relevant") is False:
        return AgentRunResult(
            relevant=False,
            reason=str(payload.get("reason") or "irrelevant"),
            tool_calls=called,
            leakage_count=leakage,
            model_id=model_id,
            raw_final=final_text,
        )

    # Validate claim from agent JSON or rebuild via deterministic extractor
    claim = _claim_from_payload(payload, tools, accession)
    if claim is None:
        return AgentRunResult(
            relevant=False,
            reason="invalid_or_unquoted_claim",
            tool_calls=called,
            leakage_count=leakage,
            model_id=model_id,
            needs_review=True,
            raw_final=final_text,
        )

    assessment = payload.get("assessment")
    return AgentRunResult(
        relevant=True,
        claim=claim,
        assessment=assessment,
        tool_calls=called,
        leakage_count=leakage,
        model_id=model_id,
        needs_review=bool(payload.get("needs_review") or claim.needs_review),
        raw_final=final_text,
    )


def _claim_from_payload(
    payload: dict[str, Any], tools: AgentTools, accession: str
) -> GuidanceClaim | None:
    # Prefer validating supporting quote against fetched document text.
    source_document = payload.get("source_document")
    supporting_quote = payload.get("supporting_quote")
    if not source_document or not supporting_quote:
        return _extract_via_tools(tools, accession)
    doc = tools.fetch_filing_document(accession, source_document)
    if not doc.ok or doc.data is None:
        return None
    text = doc.data.text
    if not quote_appears_in_source(str(supporting_quote), text):
        return None
    try:
        return GuidanceClaim.model_validate(payload)
    except Exception:
        return _extract_via_tools(tools, accession)


def _extract_via_tools(tools: AgentTools, accession: str) -> GuidanceClaim | None:
    meta_r = tools.get_filing_metadata(accession)
    docs_r = tools.list_filing_documents(accession)
    if not meta_r.ok or not docs_r.ok:
        return None
    meta = meta_r.data
    filename = select_exhibit99(docs_r.data)
    if not filename:
        return None
    content_r = tools.fetch_filing_document(accession, filename)
    if not content_r.ok:
        return None
    return extract_guidance_from_text(
        text=content_r.data.text,
        meta_accession=meta.accession,
        meta_cik=meta.cik,
        meta_ticker=meta.ticker or "UNKNOWN",
        meta_filing_date=meta.filing_date,
        meta_accepted_at=meta.accepted_at,
        source_document=filename,
    )


def _deterministic_fallback(
    accession: str,
    tools: AgentTools,
    called: list[str],
    leakage: int,
    model_id: str | None,
    raw_final: str,
) -> AgentRunResult:
    claim = _extract_via_tools(tools, accession)
    if claim is None:
        return AgentRunResult(
            relevant=False,
            reason="unparseable_final_and_no_guidance",
            tool_calls=called,
            leakage_count=leakage,
            model_id=model_id,
            raw_final=raw_final,
        )
    return AgentRunResult(
        relevant=True,
        claim=claim,
        tool_calls=called,
        leakage_count=leakage,
        model_id=model_id,
        needs_review=True,
        raw_final=raw_final,
    )


def required_tools_for_relevant() -> set[str]:
    return {
        "get_filing_metadata",
        "list_filing_documents",
        "fetch_filing_document",
    }
