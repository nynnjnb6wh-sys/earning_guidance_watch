"""Default watchlist companies (MVP: AMD, INTC, NVDA)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WatchCompany:
    ticker: str
    cik: str
    name: str
    fiscal_year_end_month: int  # calendar month of fiscal year end


DEFAULT_WATCHLIST: tuple[WatchCompany, ...] = (
    WatchCompany("AMD", "0000002488", "Advanced Micro Devices, Inc.", 12),
    WatchCompany("INTC", "0000050863", "Intel Corporation", 12),
    WatchCompany("NVDA", "0001045810", "NVIDIA Corporation", 1),
)


def by_ticker(ticker: str) -> WatchCompany:
    key = ticker.upper()
    for company in DEFAULT_WATCHLIST:
        if company.ticker == key:
            return company
    raise KeyError(f"Unknown watchlist ticker: {ticker}")
