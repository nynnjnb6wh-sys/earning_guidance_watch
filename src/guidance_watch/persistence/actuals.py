"""Load and persist curated actual revenue results."""

from __future__ import annotations

import csv
import sqlite3
from datetime import date
from pathlib import Path

from guidance_watch.analysis.linker import ActualResult
from guidance_watch.models import FiscalPeriod


def load_actuals_csv(path: Path) -> list[ActualResult]:
    rows: list[ActualResult] = []
    with path.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(
                ActualResult(
                    ticker=row["ticker"].strip().upper(),
                    cik=row["cik"].strip(),
                    target_fiscal_period=FiscalPeriod.parse(row["target_fiscal_period"].strip()),
                    actual_revenue_usd_m=float(row["actual_revenue_usd_m"]),
                    actual_publication_date=date.fromisoformat(row["actual_publication_date"]),
                    source=row.get("source") or "seed",
                )
            )
    return rows


def upsert_actual(conn: sqlite3.Connection, actual: ActualResult) -> None:
    conn.execute(
        """
        INSERT INTO actual_results (
            cik, target_fiscal_period, actual_revenue_usd_m, actual_publication_date, source
        ) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(cik, target_fiscal_period, actual_publication_date)
        DO UPDATE SET actual_revenue_usd_m = excluded.actual_revenue_usd_m, source = excluded.source
        """,
        (
            actual.cik,
            actual.target_fiscal_period.label,
            actual.actual_revenue_usd_m,
            actual.actual_publication_date.isoformat(),
            actual.source,
        ),
    )


def load_actuals_for_cik(conn: sqlite3.Connection, cik: str) -> list[ActualResult]:
    rows = conn.execute(
        """
        SELECT cik, target_fiscal_period, actual_revenue_usd_m, actual_publication_date, source
        FROM actual_results WHERE cik = ?
        """,
        (cik,),
    ).fetchall()
    # ticker not stored on actual_results — leave blank
    return [
        ActualResult(
            ticker="",
            cik=r["cik"],
            target_fiscal_period=FiscalPeriod.parse(r["target_fiscal_period"]),
            actual_revenue_usd_m=float(r["actual_revenue_usd_m"]),
            actual_publication_date=date.fromisoformat(r["actual_publication_date"]),
            source=r["source"] or "db",
        )
        for r in rows
    ]


def seed_actuals(conn: sqlite3.Connection, csv_path: Path) -> int:
    actuals = load_actuals_csv(csv_path)
    for actual in actuals:
        upsert_actual(conn, actual)
    conn.commit()
    return len(actuals)
