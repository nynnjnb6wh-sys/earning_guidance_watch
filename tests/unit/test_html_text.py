"""HTML extraction and quote verification."""

from __future__ import annotations

import pytest

from guidance_watch.sec.html_text import html_to_text, quote_appears_in_source


@pytest.mark.unit
def test_html_to_text_strips_tags() -> None:
    html = "<html><body><p>Revenue is expected to be $5.4 billion</p></body></html>"
    text = html_to_text(html)
    assert "Revenue is expected to be $5.4 billion" in text
    assert "<p>" not in text


@pytest.mark.unit
def test_quote_must_appear_exactly_after_normalize() -> None:
    source = "Revenue   is expected\nto be $5.4 billion to $6.0 billion."
    assert quote_appears_in_source(
        "Revenue is expected to be $5.4 billion to $6.0 billion.", source
    )
    assert not quote_appears_in_source("Revenue will be $99 billion", source)
