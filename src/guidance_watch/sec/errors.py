"""SEC client errors."""

from __future__ import annotations


class SecError(Exception):
    """Base SEC client error."""


class SecHttpError(SecError):
    def __init__(self, status_code: int, url: str, detail: str | None = None) -> None:
        self.status_code = status_code
        self.url = url
        self.detail = detail
        super().__init__(f"SEC HTTP {status_code} for {url}: {detail or ''}".strip())


class SecRetryExhausted(SecError):
    def __init__(self, url: str, attempts: int, last_error: str) -> None:
        self.url = url
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(f"SEC retries exhausted for {url} after {attempts} attempts: {last_error}")
