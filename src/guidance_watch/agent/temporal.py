"""Temporal-safety guard: reject tool results published after the cutoff."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any


@dataclass
class TemporalLeakageError(Exception):
    """Raised when a tool result is dated after the analysis cutoff."""

    tool_name: str
    cutoff: datetime
    offending_date: datetime | date
    detail: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return (
            f"temporal leakage in {self.tool_name}: {self.offending_date} "
            f"after cutoff {self.cutoff.isoformat()} ({self.detail})"
        )


def as_utc_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def ensure_not_after_cutoff(
    *,
    tool_name: str,
    cutoff: datetime,
    published: datetime | date | None,
    detail: str = "",
) -> None:
    if published is None:
        return
    cutoff_aware = as_utc_aware(cutoff)
    if isinstance(published, datetime):
        pub = as_utc_aware(published)
        if pub > cutoff_aware:
            raise TemporalLeakageError(tool_name, cutoff_aware, pub, detail)
        return
    cutoff_date = cutoff_aware.date()
    if published > cutoff_date:
        raise TemporalLeakageError(tool_name, cutoff_aware, published, detail)


def filter_history_before_cutoff(
    history: list[Any],
    cutoff: datetime,
    *,
    tool_name: str = "get_company_history",
) -> list[Any]:
    """Return outcomes whose publication date is on/before cutoff.

    Raises TemporalLeakageError if any provided outcome is after cutoff.
    """
    kept: list[Any] = []
    for row in history:
        pub = getattr(row, "actual_publication_date", None)
        ensure_not_after_cutoff(
            tool_name=tool_name,
            cutoff=cutoff,
            published=pub,
            detail=f"guidance_claim_id={getattr(row, 'guidance_claim_id', None)}",
        )
        kept.append(row)
    return kept
