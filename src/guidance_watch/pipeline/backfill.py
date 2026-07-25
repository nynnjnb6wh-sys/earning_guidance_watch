"""Backfill historical guidance extraction and actuals linking."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from guidance_watch.analysis.linker import link_claims_for_period
from guidance_watch.config import Settings, get_settings
from guidance_watch.models import GuidanceClaim
from guidance_watch.persistence import repository as repo
from guidance_watch.persistence.actuals import load_actuals_csv, seed_actuals
from guidance_watch.persistence.db import init_db
from guidance_watch.persistence.outcomes import upsert_outcome
from guidance_watch.pipeline.analyze import analyze_accession
from guidance_watch.sec.watchlist import by_ticker


@dataclass
class BackfillResult:
    ticker: str
    accessions_seen: int = 0
    claims_extracted: int = 0
    outcomes_linked: int = 0
    needs_review: list[str] = field(default_factory=list)


def discover_accessions(fixtures_root: Path, ticker: str) -> list[str]:
    """Find accessions under fixtures/filings or edgar_raw/{TICKER}."""
    accessions: list[str] = []
    filings = fixtures_root / "filings"
    ticker_dir = fixtures_root / ticker.upper()
    if filings.is_dir():
        for child in sorted(filings.iterdir()):
            if (child / "metadata.json").is_file():
                # Filter by ticker in metadata when present
                import json

                meta = json.loads((child / "metadata.json").read_text())
                if meta.get("ticker", "").upper() == ticker.upper() or not meta.get("ticker"):
                    accessions.append(child.name)
    if ticker_dir.is_dir():
        for child in sorted(ticker_dir.iterdir()):
            if child.is_dir() and (child / "metadata.json").is_file():
                accessions.append(child.name)
    # de-dupe preserve order
    seen: set[str] = set()
    ordered: list[str] = []
    for acc in accessions:
        if acc not in seen:
            seen.add(acc)
            ordered.append(acc)
    return ordered


def run_backfill(
    *,
    ticker: str,
    quarters: int = 8,
    fixtures_root: Path,
    actuals_csv: Path,
    settings: Settings | None = None,
) -> BackfillResult:
    settings = settings or get_settings()
    company = by_ticker(ticker)
    conn = init_db(settings.db_path)
    result = BackfillResult(ticker=company.ticker)
    try:
        repo.ensure_company(conn, cik=company.cik, ticker=company.ticker, name=company.name)
        seed_actuals(conn, actuals_csv)
        actuals = {
            a.target_fiscal_period.label: a
            for a in load_actuals_csv(actuals_csv)
            if a.cik == company.cik or a.ticker == company.ticker
        }

        accessions = discover_accessions(fixtures_root, company.ticker)
        claims_by_period: dict[str, list[GuidanceClaim]] = defaultdict(list)

        for accession in accessions:
            result.accessions_seen += 1
            # Allow re-analyze by clearing run if we need claims — for backfill,
            # skip if already completed unless no claim exists.
            existing = repo.get_analysis_run(conn, accession)
            if existing is None:
                analyze_accession(accession, fixtures_root=fixtures_root, settings=settings)

            rows = conn.execute(
                "SELECT * FROM guidance_claims WHERE accession = ?",
                (accession,),
            ).fetchall()
            for row in rows:
                from datetime import datetime

                from guidance_watch.models import FiscalPeriod, RevisionDirection

                claim = GuidanceClaim(
                    claim_id=row["claim_id"],
                    ticker=row["ticker"],
                    cik=row["cik"],
                    accession=row["accession"],
                    filing_date=row["filing_date"],
                    accepted_at=datetime.fromisoformat(row["accepted_at"]),
                    source_document=row["source_document"],
                    target_fiscal_period=FiscalPeriod.parse(row["target_fiscal_period"]),
                    lower_bound_usd_m=float(row["lower_bound_usd_m"]),
                    upper_bound_usd_m=float(row["upper_bound_usd_m"]),
                    unit_in_source=row["unit_in_source"],
                    is_revision=bool(row["is_revision"]),
                    revision_direction=RevisionDirection(row["revision_direction"]),
                    supporting_quote=row["supporting_quote"],
                    confidence=float(row["confidence"]),
                    needs_review=bool(row["needs_review"]),
                )
                claims_by_period[claim.target_fiscal_period.label].append(claim)
                result.claims_extracted += 1

        # Link oldest periods first, limited by quarters
        period_labels = sorted(claims_by_period.keys())[-quarters:]
        for label in period_labels:
            link = link_claims_for_period(claims_by_period[label], actuals.get(label))
            if link.needs_review or link.outcome is None:
                result.needs_review.append(f"{label}:{link.reason}")
                continue
            upsert_outcome(conn, link.outcome)
            result.outcomes_linked += 1
        conn.commit()
        return result
    finally:
        conn.close()
