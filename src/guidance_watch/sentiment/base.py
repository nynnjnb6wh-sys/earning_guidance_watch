"""Sentiment provider protocol."""

from __future__ import annotations

from typing import Protocol

from guidance_watch.models import SentimentResult


class SentimentProvider(Protocol):
    def analyze(self, text: str) -> SentimentResult: ...
