"""Persistence helpers for filings, claims, runs, and reports."""

from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from guidance_watch.models import FilingMetadata, GuidanceClaim, ReliabilityAssessment


def ensure_company(
    conn: sqlite3.Connection, *, cik: str, ticker: str, name: str | None = None
) -> None:
    conn.execute(
        """
        INSERT INTO companies (cik, ticker, name)
        VALUES (?, ?, ?)
        ON CONFLICT(cik) DO UPDATE SET ticker = excluded.ticker
        """,
        (cik, ticker, name),
    )


def upsert_filing(conn: sqlite3.Connection, meta: FilingMetadata) -> None:
    ensure_company(conn, cik=meta.cik, ticker=meta.ticker or "UNKNOWN")
    conn.execute(
        """
        INSERT INTO filings (
            accession, cik, ticker, form, filing_date, accepted_at, primary_document, items_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(accession) DO NOTHING
        """,
        (
            meta.accession,
            meta.cik,
            meta.ticker,
            meta.form,
            meta.filing_date,
            meta.accepted_at.isoformat(),
            meta.primary_document,
            json.dumps(meta.items),
        ),
    )


def get_analysis_run(conn: sqlite3.Connection, accession: str) -> sqlite3.Row | None:
    row: sqlite3.Row | None = conn.execute(
        "SELECT * FROM analysis_runs WHERE accession = ?", (accession,)
    ).fetchone()
    return row


def insert_job_attempt(
    conn: sqlite3.Connection, *, accession: str, status: str, detail: str | None = None
) -> None:
    conn.execute(
        "INSERT INTO job_attempts (accession, status, detail) VALUES (?, ?, ?)",
        (accession, status, detail),
    )


def insert_guidance_claim(conn: sqlite3.Connection, claim: GuidanceClaim) -> str:
    claim_id = claim.claim_id or str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO guidance_claims (
            claim_id, ticker, cik, accession, filing_date, accepted_at, source_document,
            target_fiscal_period, metric, gaap_or_non_gaap, lower_bound_usd_m, upper_bound_usd_m,
            currency, unit_in_source, is_revision, revision_direction, supporting_quote,
            confidence, needs_review
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            claim_id,
            claim.ticker,
            claim.cik,
            claim.accession,
            claim.filing_date,
            claim.accepted_at.isoformat(),
            claim.source_document,
            claim.target_fiscal_period.label,
            claim.metric,
            claim.gaap_or_non_gaap,
            claim.lower_bound_usd_m,
            claim.upper_bound_usd_m,
            claim.currency,
            claim.unit_in_source,
            int(claim.is_revision),
            claim.revision_direction.value,
            claim.supporting_quote,
            claim.confidence,
            int(claim.needs_review),
        ),
    )
    return claim_id


def insert_analysis_run(
    conn: sqlite3.Connection,
    *,
    accession: str,
    ticker: str | None,
    cik: str | None,
    status: str,
    prompt_version: str,
    agent_version: str,
    scoring_version: str,
    model_identifier: str | None,
    assessment: ReliabilityAssessment | None,
    ignore_reason: str | None = None,
) -> str:
    run_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO analysis_runs (
            run_id, accession, ticker, cik, status, ignore_reason,
            prompt_version, agent_version, scoring_version, model_identifier, assessment_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            accession,
            ticker,
            cik,
            status,
            ignore_reason,
            prompt_version,
            agent_version,
            scoring_version,
            model_identifier,
            assessment.model_dump_json() if assessment else None,
        ),
    )
    return run_id


def insert_report(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    accession: str,
    fmt: str,
    body: str,
    path: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO reports (run_id, accession, format, path, body)
        VALUES (?, ?, ?, ?, ?)
        """,
        (run_id, accession, fmt, path, body),
    )


def count_guidance_claims(conn: sqlite3.Connection, accession: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM guidance_claims WHERE accession = ?", (accession,)
    ).fetchone()
    return int(row["n"]) if row else 0


def load_reports(conn: sqlite3.Connection, accession: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT format, path, body, created_at FROM reports WHERE accession = ?",
        (accession,),
    ).fetchall()
    return [dict(r) for r in rows]
