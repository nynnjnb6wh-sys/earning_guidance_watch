"""HTML text extraction and supporting-quote verification."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

_WS_RE = re.compile(r"\s+")


def normalize_whitespace(text: str) -> str:
    return _WS_RE.sub(" ", text).strip()


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return normalize_whitespace(soup.get_text(separator=" "))


def quote_appears_in_source(quote: str, source_text: str) -> bool:
    """Return True if the normalized quote is an exact substring of normalized source."""
    q = normalize_whitespace(quote)
    s = normalize_whitespace(source_text)
    if not q:
        return False
    return q in s
