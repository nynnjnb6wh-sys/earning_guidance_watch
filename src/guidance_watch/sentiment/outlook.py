"""Locate outlook/guidance section text for sentiment analysis."""

from __future__ import annotations

import re

_HEADING_RE = re.compile(
    r"(?is)(?:^|\n)\s*(outlook|guidance|financial\s+outlook|business\s+outlook)"
    r"\s*\n+(.*?)(?=\n\s*[A-Z][A-Za-z ]{2,40}\n|\Z)"
)


def locate_outlook_section(text: str) -> tuple[str, str]:
    """Return (section_text, method). Falls back to full text."""
    match = _HEADING_RE.search(text)
    if match:
        body = match.group(2).strip()
        if body:
            return body, "heading_regex"
    # Heuristic: take window around first 'outlook' mention
    idx = text.lower().find("outlook")
    if idx >= 0:
        start = max(0, idx - 100)
        end = min(len(text), idx + 1200)
        return text[start:end].strip(), "window_around_outlook"
    return text.strip(), "full_text"
