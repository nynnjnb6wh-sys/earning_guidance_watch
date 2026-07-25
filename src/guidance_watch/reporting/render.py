"""JSON and Markdown report rendering with citations."""

from __future__ import annotations

import json
from typing import Any

from guidance_watch.models import GuidanceClaim, ReliabilityAssessment


def edgar_filing_url(cik: str, accession: str, filename: str) -> str:
    cik_num = str(int(cik))  # strip leading zeros for directory
    acc_nodash = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{cik_num}/{acc_nodash}/{filename}"


def build_report_payload(
    claim: GuidanceClaim,
    assessment: ReliabilityAssessment,
) -> dict[str, Any]:
    citation_url = edgar_filing_url(claim.cik, claim.accession, claim.source_document)
    return {
        "current_guidance": {
            "ticker": claim.ticker,
            "target_fiscal_period": claim.target_fiscal_period.label,
            "lower_bound_usd_m": claim.lower_bound_usd_m,
            "upper_bound_usd_m": claim.upper_bound_usd_m,
            "metric": claim.metric,
            "gaap_or_non_gaap": claim.gaap_or_non_gaap,
            "source_document": claim.source_document,
            "accession": claim.accession,
            "citation_url": citation_url,
            "supporting_quote": claim.supporting_quote,
        },
        "historical_sample_size": assessment.usable_quarters,
        "original_range_hit_rate": assessment.original_range_hit_rate,
        "latest_range_hit_rate": assessment.latest_range_hit_rate,
        "median_signed_error_pct": assessment.median_signed_error_pct,
        "observed_tendency": (
            assessment.observed_tendency.value if assessment.observed_tendency else None
        ),
        "mean_absolute_error_pct": assessment.mean_absolute_error_pct,
        "revision_frequency": assessment.revision_frequency,
        "downward_revision_frequency": assessment.downward_revision_frequency,
        "current_tone_score": assessment.current_tone_score,
        "historical_median_tone": assessment.historical_median_tone,
        "tone_anomaly": assessment.tone_anomaly,
        "tone_unusual": assessment.tone_unusual,
        "component_scores": {
            "historical_hit_score": assessment.historical_hit_score,
            "revision_score": assessment.revision_score,
            "tone_consistency_score": assessment.tone_consistency_score,
        },
        "total_score": assessment.total_score,
        "reliability_label": assessment.label.value,
        "sample_size_caveat": assessment.sample_size_caveat,
        "limitations": assessment.limitations,
        "needs_review": claim.needs_review,
        "citations": [
            {
                "claim": "current_revenue_guidance_range",
                "url": citation_url,
                "excerpt": claim.supporting_quote,
            }
        ],
    }


def render_json_report(claim: GuidanceClaim, assessment: ReliabilityAssessment) -> str:
    payload = build_report_payload(claim, assessment)
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def render_markdown_report(claim: GuidanceClaim, assessment: ReliabilityAssessment) -> str:
    payload = build_report_payload(claim, assessment)
    cg = payload["current_guidance"]
    lines = [
        f"# Guidance assessment — {cg['ticker']} {cg['target_fiscal_period']}",
        "",
        "## Current guidance",
        "",
        f"- Range: **{cg['lower_bound_usd_m']}–{cg['upper_bound_usd_m']} USD millions** "
        f"(GAAP revenue)",
        f"- Accession: `{cg['accession']}`",
        f"- Source document: `{cg['source_document']}`",
        f"- Citation: {cg['citation_url']}",
        f'- Supporting quote: "{cg["supporting_quote"]}"',
        "",
        "## Historical reliability (heuristic)",
        "",
        f"- Usable quarters: {payload['historical_sample_size']}",
        f"- Original range hit rate: {payload['original_range_hit_rate']}",
        f"- Latest range hit rate: {payload['latest_range_hit_rate']}",
        f"- Median signed error (%): {payload['median_signed_error_pct']}",
        f"- Observed tendency: {payload['observed_tendency']}",
        f"- Mean absolute error (%): {payload['mean_absolute_error_pct']}",
        f"- Revision frequency: {payload['revision_frequency']}",
        f"- Downward-revision frequency: {payload['downward_revision_frequency']}",
        "",
        "## Tone",
        "",
        f"- Current tone: {payload['current_tone_score']}",
        f"- Historical median tone: {payload['historical_median_tone']}",
        f"- Tone anomaly: {payload['tone_anomaly']}",
        "",
        "## Score",
        "",
        f"- Historical hit score: {payload['component_scores']['historical_hit_score']}",
        f"- Revision score: {payload['component_scores']['revision_score']}",
        f"- Tone consistency score: {payload['component_scores']['tone_consistency_score']}",
        f"- Total score: {payload['total_score']}",
        f"- Reliability label: **{payload['reliability_label']}**",
        "",
        "## Limitations",
        "",
    ]
    if payload["limitations"]:
        lines.extend(f"- {lim}" for lim in payload["limitations"])
    else:
        lines.append("- None recorded.")
    lines.append("")
    return "\n".join(lines)
