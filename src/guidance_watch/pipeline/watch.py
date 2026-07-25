"""Watch pipeline: poll EDGAR → materialize → analyze new accessions."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from guidance_watch.config import Settings, get_settings
from guidance_watch.persistence.db import init_db
from guidance_watch.pipeline.analyze import AnalyzeResult, analyze_accession
from guidance_watch.sec.cache import ResponseCache
from guidance_watch.sec.client import SecClient
from guidance_watch.sec.documents import materialize_filing
from guidance_watch.sec.poller import PollResult, poll_watchlist
from guidance_watch.sec.watchlist import DEFAULT_WATCHLIST, WatchCompany
from guidance_watch.telemetry import setup_tracing, span


@dataclass
class WatchCycleResult:
    poll: PollResult
    analyses: list[AnalyzeResult]


def build_sec_client(
    settings: Settings, conn: object, transport: object | None = None
) -> SecClient:
    cache = ResponseCache(settings.cache_dir, conn)  # type: ignore[arg-type]
    return SecClient(
        user_agent=settings.sec_user_agent,
        cache=cache,
        requests_per_second=settings.sec_requests_per_second,
        transport=transport,  # type: ignore[arg-type]
    )


def run_watch_once(
    *,
    settings: Settings | None = None,
    companies: tuple[WatchCompany, ...] = DEFAULT_WATCHLIST,
    transport: object | None = None,
    analyze: bool = True,
    materialize_root: Path | None = None,
) -> WatchCycleResult:
    settings = settings or get_settings()
    setup_tracing()
    conn = init_db(settings.db_path)
    try:
        client = build_sec_client(settings, conn, transport=transport)
        with span("poll", companies=len(companies)):
            poll = poll_watchlist(client, conn, companies=companies)
        analyses: list[AnalyzeResult] = []
        if analyze:
            dest = materialize_root or (settings.cache_dir / "filings")
            dest.mkdir(parents=True, exist_ok=True)
            for detected in poll.detected:
                with span(
                    "detect",
                    ticker=detected.company.ticker,
                    accession=detected.metadata.accession,
                ):
                    materialize_filing(client, detected.metadata, dest)
                analyses.append(
                    analyze_accession(
                        detected.metadata.accession,
                        fixtures_root=dest,
                        settings=settings,
                    )
                )
        return WatchCycleResult(poll=poll, analyses=analyses)
    finally:
        conn.close()


def run_watch_loop(
    *,
    interval_s: int,
    settings: Settings | None = None,
    companies: tuple[WatchCompany, ...] = DEFAULT_WATCHLIST,
    transport: object | None = None,
    max_cycles: int | None = None,
) -> list[WatchCycleResult]:
    """In-process sleep loop (D15). ``max_cycles`` is for tests."""
    results: list[WatchCycleResult] = []
    cycles = 0
    while True:
        results.append(
            run_watch_once(
                settings=settings,
                companies=companies,
                transport=transport,
            )
        )
        cycles += 1
        if max_cycles is not None and cycles >= max_cycles:
            break
        time.sleep(interval_s)
    return results
