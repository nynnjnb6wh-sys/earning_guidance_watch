"""SEC EDGAR HTTP client with pacing, retries, and response caching."""

from __future__ import annotations

import json
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from guidance_watch.sec.cache import ResponseCache
from guidance_watch.sec.errors import SecHttpError, SecRetryExhausted

RetryableStatus = {429, 500, 502, 503, 504}


@dataclass
class RequestStats:
    requests: int = 0
    cache_hits: int = 0
    retries: int = 0
    last_status: int | None = None


@dataclass
class SecClient:
    """httpx-backed SEC client.

    Pass a custom ``transport`` (e.g. ``httpx.MockTransport``) for offline tests.
    """

    user_agent: str
    cache: ResponseCache | None = None
    requests_per_second: float = 4.0
    max_retries: int = 4
    base_backoff_s: float = 0.05
    transport: httpx.BaseTransport | None = None
    sleep: Callable[[float], None] = field(default=time.sleep)
    monotonic: Callable[[], float] = field(default=time.monotonic)
    stats: RequestStats = field(default_factory=RequestStats)
    _last_request_at: float = field(default=0.0, init=False)

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept-Encoding": "gzip, deflate",
        }

    def _pace(self) -> None:
        if self.requests_per_second <= 0:
            return
        min_interval = 1.0 / self.requests_per_second
        now = self.monotonic()
        wait = self._last_request_at + min_interval - now
        if wait > 0:
            self.sleep(wait)
        self._last_request_at = self.monotonic()

    def _client(self) -> httpx.Client:
        return httpx.Client(
            headers=self._headers(),
            timeout=60.0,
            follow_redirects=True,
            transport=self.transport,
        )

    def get_bytes(
        self,
        url: str,
        *,
        use_cache: bool = True,
        allow_statuses: set[int] | None = None,
    ) -> tuple[int, bytes, bool]:
        """GET bytes. Returns (status_code, body, from_cache)."""
        allow = allow_statuses or {200}
        if use_cache and self.cache is not None:
            hit = self.cache.get(url)
            if hit is not None:
                self.stats.cache_hits += 1
                self.stats.last_status = hit.status_code
                return hit.status_code, hit.body, True

        last_error = ""
        with self._client() as client:
            for attempt in range(self.max_retries + 1):
                self._pace()
                self.stats.requests += 1
                try:
                    response = client.get(url)
                except httpx.TimeoutException as exc:
                    last_error = f"timeout: {exc}"
                    if attempt >= self.max_retries:
                        raise SecRetryExhausted(url, attempt + 1, last_error) from exc
                    self.stats.retries += 1
                    self._backoff(attempt)
                    continue

                self.stats.last_status = response.status_code
                if response.status_code in allow:
                    body = response.content
                    if use_cache and self.cache is not None and response.status_code == 200:
                        self.cache.put(url, status_code=response.status_code, body=body)
                    return response.status_code, body, False

                if response.status_code in RetryableStatus and attempt < self.max_retries:
                    last_error = f"HTTP {response.status_code}"
                    self.stats.retries += 1
                    self._backoff(attempt, retry_after=response.headers.get("Retry-After"))
                    continue

                raise SecHttpError(response.status_code, url, response.text[:200])

        raise SecRetryExhausted(url, self.max_retries + 1, last_error or "unknown")

    def get_json(self, url: str, *, use_cache: bool = True) -> Any:
        status, body, _ = self.get_bytes(url, use_cache=use_cache)
        if status != 200:
            raise SecHttpError(status, url)
        return json.loads(body.decode("utf-8"))

    def _backoff(self, attempt: int, retry_after: str | None = None) -> None:
        if retry_after:
            try:
                self.sleep(float(retry_after))
                return
            except ValueError:
                pass
        delay = self.base_backoff_s * (2**attempt)
        delay += random.uniform(0, self.base_backoff_s)
        self.sleep(delay)


def submissions_url(cik: str) -> str:
    return f"https://data.sec.gov/submissions/CIK{cik}.json"


def company_tickers_url() -> str:
    return "https://www.sec.gov/files/company_tickers.json"


def filing_index_url(cik: str, accession: str) -> str:
    cik_num = str(int(cik))
    acc = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{cik_num}/{acc}/index.json"


def filing_document_url(cik: str, accession: str, filename: str) -> str:
    cik_num = str(int(cik))
    acc = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{cik_num}/{acc}/{filename}"
