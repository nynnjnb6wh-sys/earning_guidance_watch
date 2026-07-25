"""EDGAR timestamp parsing — Eastern wall times normalized to UTC."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

_EASTERN = ZoneInfo("America/New_York")


def parse_edgar_accepted_at(value: str) -> datetime:
    """Parse EDGAR acceptanceDateTime into timezone-aware UTC datetime.

    EDGAR values look like ``2024-01-30T16:05:12.000`` (Eastern, no offset)
    or may already include an offset / ``Z``.
    """
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    # Trim milliseconds without offset for fromisoformat compatibility quirks
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        # e.g. 2024-01-30T16:05:12.000
        if "." in raw and "+" not in raw[10:] and raw.count("-") == 2:
            main, frac = raw.split(".", 1)
            frac = "".join(ch for ch in frac if ch.isdigit())[:6].ljust(6, "0")
            dt = datetime.fromisoformat(f"{main}.{frac}")
        else:
            raise
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_EASTERN)
    return dt.astimezone(ZoneInfo("UTC"))
