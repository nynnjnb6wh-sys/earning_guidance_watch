"""Deterministic fake sentiment provider for offline tests."""

from __future__ import annotations

import hashlib

from guidance_watch.models import SentimentResult


class FakeSentimentProvider:
    def __init__(
        self,
        *,
        positive: float = 0.4,
        neutral: float = 0.4,
        negative: float = 0.2,
        model_name: str = "fake-sentiment",
        model_revision: str = "test",
    ) -> None:
        self.positive = positive
        self.neutral = neutral
        self.negative = negative
        self.model_name = model_name
        self.model_revision = model_revision

    def analyze(self, text: str) -> SentimentResult:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return SentimentResult.from_probabilities(
            model_name=self.model_name,
            model_revision=self.model_revision,
            positive_probability=self.positive,
            neutral_probability=self.neutral,
            negative_probability=self.negative,
            analyzed_text_hash=digest,
        )
