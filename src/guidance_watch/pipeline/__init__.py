"""End-to-end pipelines."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from guidance_watch.pipeline.analyze import AnalyzeResult, analyze_accession

__all__ = ["AnalyzeResult", "analyze_accession"]


def __getattr__(name: str) -> object:
    if name in {"AnalyzeResult", "analyze_accession"}:
        from guidance_watch.pipeline import analyze as _analyze

        return getattr(_analyze, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
