"""FinBERT sentiment provider (optional dependency: transformers + torch)."""

from __future__ import annotations

import hashlib
from typing import Any

from guidance_watch.models import SentimentResult

DEFAULT_MODEL = "ProsusAI/finbert"
MAX_LENGTH = 512


class FinBertProvider:
    """Lazy-loading FinBERT classifier with token-window averaging."""

    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        self.model_name = model_name
        self._pipe: Any | None = None
        self._model_revision: str = "unknown"

    def _ensure_loaded(self) -> None:
        if self._pipe is not None:
            return
        try:
            from transformers import AutoConfig, pipeline
        except ImportError as exc:  # pragma: no cover - optional extra
            raise RuntimeError(
                "FinBERT requires the 'finbert' extra: uv sync --extra finbert"
            ) from exc
        config = AutoConfig.from_pretrained(self.model_name)
        self._model_revision = str(
            getattr(config, "_name_or_path", None)
            or getattr(config, "name_or_path", None)
            or self.model_name
        )
        self._pipe = pipeline(
            "text-classification",
            model=self.model_name,
            tokenizer=self.model_name,
            top_k=None,
            function_to_return="all",
            truncation=True,
            padding=True,
        )

    def analyze(self, text: str) -> SentimentResult:
        self._ensure_loaded()
        assert self._pipe is not None
        windows = _chunk_text(text, max_chars=2000)
        if not windows:
            windows = [""]
        agg = {"positive": 0.0, "neutral": 0.0, "negative": 0.0}
        weights = 0.0
        for window in windows:
            outputs = self._pipe(window)
            # transformers may return list[list[dict]] or list[dict]
            labels = outputs[0] if outputs and isinstance(outputs[0], list) else outputs
            weight = max(len(window.split()), 1)
            for item in labels:
                label = str(item["label"]).lower()
                score = float(item["score"])
                if label in agg:
                    agg[label] += score * weight
            weights += weight
        if weights <= 0:
            weights = 1.0
        pos = agg["positive"] / weights
        neu = agg["neutral"] / weights
        neg = agg["negative"] / weights
        total = pos + neu + neg
        if total > 0:
            pos, neu, neg = pos / total, neu / total, neg / total
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return SentimentResult.from_probabilities(
            model_name=self.model_name,
            model_revision=self._model_revision,
            positive_probability=pos,
            neutral_probability=neu,
            negative_probability=neg,
            analyzed_text_hash=digest,
        )


def _chunk_text(text: str, max_chars: int = 2000) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        chunks.append(text[start : start + max_chars])
        start += max_chars
    return chunks
