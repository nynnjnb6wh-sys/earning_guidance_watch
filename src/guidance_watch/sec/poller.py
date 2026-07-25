"""Deterministic EDGAR submissions poller for Form 8-K Items 2.02 / 7.01."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime

from guidance_watch.models import FilingMetadata
from guidance_watch.persistence import repository as repo
from guidance_watch.sec.client import SecClient, submissions_url
from guidance_watch.sec.timestamps import parse_edgar_accepted_at
from guidance_watch.sec.watchlist import DEFAULT_WATCHLIST, WatchCompany

TARGET_FORMS = {"8-K", "8-K/A"}
TARGET_ITEMS = {"2.02", "7.01"}


@dataclass
class DetectedFiling:
    company: WatchCompany
    metadata: FilingMetadata


@dataclass
class PollResult:
    detected: list[DetectedFiling]
    skipped_duplicate: int = 0
    companies_polled: int = 0


def _items_match(items_field: str) -> bool:
    if not items_field or not items_field.strip():
        # Some 8-Ks omit items in the recent feed; keep them for inspection.
        return True
    parts = {p.strip() for p in items_field.split(",") if p.strip()}
    return bool(parts & TARGET_ITEMS)


def get_cursor(conn: sqlite3.Connection, cik: str) -> tuple[str | None, str | None]:
    row = conn.execute(
        "SELECT last_accession, last_accepted_at FROM filing_cursors WHERE cik = ?",
        (cik,),
    ).fetchone()
    if row is None:
        return None, None
    return row["last_accession"], row["last_accepted_at"]


def set_cursor(
    conn: sqlite3.Connection,
    *,
    cik: str,
    accession: str,
    accepted_at: datetime,
) -> None:
    conn.execute(
        """
        INSERT INTO filing_cursors (cik, last_accession, last_accepted_at, updated_at)
        VALUES (?, ?, ?, datetime('now'))
        ON CONFLICT(cik) DO UPDATE SET
            last_accession = excluded.last_accession,
            last_accepted_at = excluded.last_accepted_at,
            updated_at = datetime('now')
        """,
        (cik, accession, accepted_at.isoformat()),
    )


def list_new_8k_filings(
    client: SecClient,
    company: WatchCompany,
    *,
    last_accession: str | None,
) -> list[FilingMetadata]:
    """Return newer matching 8-K filings oldest-first (after cursor)."""
    data = client.get_json(submissions_url(company.cik))
    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    filed = recent.get("filingDate", [])
    accepted = recent.get("acceptanceDateTime", [])
    primary = recent.get("primaryDocument", [])
    items = recent.get("items", [])

    collected: list[FilingMetadata] = []
    for i, form in enumerate(forms):
        acc = accessions[i]
        if last_accession and acc == last_accession:
            break
        if form not in TARGET_FORMS:
            continue
        item_field = items[i] if i < len(items) else ""
        if not _items_match(item_field):
            continue
        accepted_at = parse_edgar_accepted_at(accepted[i])
        item_list = [p.strip() for p in (item_field or "").split(",") if p.strip()]
        collected.append(
            FilingMetadata(
                accession=acc,
                cik=company.cik,
                ticker=company.ticker,
                form=form,
                filing_date=filed[i],
                accepted_at=accepted_at,
                primary_document=primary[i] if i < len(primary) else None,
                items=item_list,
            )
        )
    # recent feed is newest-first; process oldest first
    collected.reverse()
    return collected


def _newest_matching(client: SecClient, company: WatchCompany) -> FilingMetadata | None:
    """Return the newest matching 8-K from the recent feed, or None."""
    data = client.get_json(submissions_url(company.cik))
    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    filed = recent.get("filingDate", [])
    accepted = recent.get("acceptanceDateTime", [])
    primary = recent.get("primaryDocument", [])
    items = recent.get("items", [])
    for i, form in enumerate(forms):
        if form not in TARGET_FORMS:
            continue
        item_field = items[i] if i < len(items) else ""
        if not _items_match(item_field):
            continue
        return FilingMetadata(
            accession=accessions[i],
            cik=company.cik,
            ticker=company.ticker,
            form=form,
            filing_date=filed[i],
            accepted_at=parse_edgar_accepted_at(accepted[i]),
            primary_document=primary[i] if i < len(primary) else None,
            items=[p.strip() for p in (item_field or "").split(",") if p.strip()],
        )
    return None


def poll_watchlist(
    client: SecClient,
    conn: sqlite3.Connection,
    *,
    companies: tuple[WatchCompany, ...] = DEFAULT_WATCHLIST,
    seen_accessions: set[str] | None = None,
) -> PollResult:
    """Poll each company; persist cursors; skip already-seen accessions.

    First poll for a company (no cursor) bootstraps the cursor to the newest
    matching 8-K without enqueueing historical backlog.
    """
    detected: list[DetectedFiling] = []
    skipped = 0
    seen = seen_accessions if seen_accessions is not None else set()

    for company in companies:
        repo.ensure_company(
            conn,
            cik=company.cik,
            ticker=company.ticker,
            name=company.name,
        )
        conn.execute(
            "UPDATE companies SET fiscal_year_end_month = ? WHERE cik = ?",
            (company.fiscal_year_end_month, company.cik),
        )
        last_acc, _ = get_cursor(conn, company.cik)
        if last_acc is None:
            newest = _newest_matching(client, company)
            if newest is not None:
                set_cursor(
                    conn,
                    cik=company.cik,
                    accession=newest.accession,
                    accepted_at=newest.accepted_at,
                )
            continue

        filings = list_new_8k_filings(client, company, last_accession=last_acc)
        newest_seen: FilingMetadata | None = None
        for meta in filings:
            if meta.accession in seen or repo.get_analysis_run(conn, meta.accession) is not None:
                skipped += 1
                newest_seen = meta
                continue
            repo.upsert_filing(conn, meta)
            repo.insert_job_attempt(conn, accession=meta.accession, status="detected")
            detected.append(DetectedFiling(company=company, metadata=meta))
            seen.add(meta.accession)
            newest_seen = meta
        if newest_seen is not None:
            set_cursor(
                conn,
                cik=company.cik,
                accession=newest_seen.accession,
                accepted_at=newest_seen.accepted_at,
            )
        # If feed unchanged (no new filings), cursor stays put — zero work.

    conn.commit()
    return PollResult(
        detected=detected,
        skipped_duplicate=skipped,
        companies_polled=len(companies),
    )
