"""Persist guidance outcomes."""

from __future__ import annotations

import json
import sqlite3

from guidance_watch.models import HistoricalOutcome


def upsert_outcome(conn: sqlite3.Connection, outcome: HistoricalOutcome) -> None:
    conn.execute(
        """
        INSERT INTO guidance_outcomes (
            guidance_claim_id, target_fiscal_period,
            original_lower_usd_m, original_upper_usd_m,
            latest_lower_usd_m, latest_upper_usd_m,
            actual_revenue_usd_m, actual_publication_date,
            revision_count, downward_revision_occurred, source_documents_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(guidance_claim_id) DO UPDATE SET
            latest_lower_usd_m = excluded.latest_lower_usd_m,
            latest_upper_usd_m = excluded.latest_upper_usd_m,
            actual_revenue_usd_m = excluded.actual_revenue_usd_m,
            actual_publication_date = excluded.actual_publication_date,
            revision_count = excluded.revision_count,
            downward_revision_occurred = excluded.downward_revision_occurred,
            source_documents_json = excluded.source_documents_json
        """,
        (
            outcome.guidance_claim_id,
            outcome.target_fiscal_period.label,
            outcome.original_lower_usd_m,
            outcome.original_upper_usd_m,
            outcome.latest_lower_usd_m,
            outcome.latest_upper_usd_m,
            outcome.actual_revenue_usd_m,
            outcome.actual_publication_date.isoformat(),
            outcome.revision_count,
            int(outcome.downward_revision_occurred),
            json.dumps(outcome.source_documents),
        ),
    )


def list_outcomes_for_cik(conn: sqlite3.Connection, cik: str) -> list[HistoricalOutcome]:
    from datetime import date

    from guidance_watch.models import FiscalPeriod

    rows = conn.execute(
        """
        SELECT o.* FROM guidance_outcomes o
        JOIN guidance_claims c ON c.claim_id = o.guidance_claim_id
        WHERE c.cik = ?
        ORDER BY o.target_fiscal_period
        """,
        (cik,),
    ).fetchall()
    results: list[HistoricalOutcome] = []
    for r in rows:
        results.append(
            HistoricalOutcome(
                guidance_claim_id=r["guidance_claim_id"],
                target_fiscal_period=FiscalPeriod.parse(r["target_fiscal_period"]),
                original_lower_usd_m=float(r["original_lower_usd_m"]),
                original_upper_usd_m=float(r["original_upper_usd_m"]),
                latest_lower_usd_m=float(r["latest_lower_usd_m"]),
                latest_upper_usd_m=float(r["latest_upper_usd_m"]),
                actual_revenue_usd_m=float(r["actual_revenue_usd_m"]),
                actual_publication_date=date.fromisoformat(r["actual_publication_date"]),
                revision_count=int(r["revision_count"]),
                downward_revision_occurred=bool(r["downward_revision_occurred"]),
                source_documents=json.loads(r["source_documents_json"] or "[]"),
            )
        )
    return results
