"""Sentiment providers and outlook locator (offline)."""

from __future__ import annotations

import pytest

from guidance_watch.sentiment import FakeSentimentProvider, locate_outlook_section


@pytest.mark.unit
def test_fake_sentiment_is_deterministic() -> None:
    provider = FakeSentimentProvider(positive=0.6, neutral=0.3, negative=0.1)
    a = provider.analyze("We expect strong demand next quarter.")
    b = provider.analyze("We expect strong demand next quarter.")
    assert a.tone_score == pytest.approx(0.5)
    assert a.analyzed_text_hash == b.analyzed_text_hash
    assert a.model_name == "fake-sentiment"


@pytest.mark.unit
def test_locate_outlook_heading() -> None:
    text = """
Results
Revenue was strong.

Outlook
Revenue is expected to be $10 billion, plus or minus 2%.

Other
Thanks.
"""
    section, method = locate_outlook_section(text)
    assert method == "heading_regex"
    assert "Revenue is expected" in section
    assert "Thanks" not in section


@pytest.mark.unit
@pytest.mark.live
def test_finbert_live_optional() -> None:
    """Optional live FinBERT weight download — deselected by default."""
    from guidance_watch.sentiment import FinBertProvider

    provider = FinBertProvider()
    result = provider.analyze("Revenue outlook is strong and demand remains robust.")
    assert abs(result.tone_score) <= 1.0
    assert result.analyzed_text_hash
