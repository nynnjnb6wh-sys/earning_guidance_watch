"""Sentiment providers (FinBERT + fakes for tests)."""

from guidance_watch.sentiment.fake import FakeSentimentProvider
from guidance_watch.sentiment.finbert import FinBertProvider
from guidance_watch.sentiment.outlook import locate_outlook_section

__all__ = [
    "FakeSentimentProvider",
    "FinBertProvider",
    "locate_outlook_section",
]
