"""Slice 3: SEC client retries/cache and poller behavior with MockTransport."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from guidance_watch.config import Settings
from guidance_watch.persistence.db import init_db
from guidance_watch.pipeline.analyze import analyze_accession
from guidance_watch.sec.cache import ResponseCache
from guidance_watch.sec.client import SecClient, submissions_url
from guidance_watch.sec.errors import SecHttpError
from guidance_watch.sec.poller import get_cursor, poll_watchlist
from guidance_watch.sec.watchlist import WatchCompany

AMD = WatchCompany("AMD", "0000002488", "Advanced Micro Devices, Inc.", 12)


def _submissions(
    *,
    accessions: list[str],
    forms: list[str] | None = None,
    items: list[str] | None = None,
) -> dict:
    n = len(accessions)
    forms = forms or ["8-K"] * n
    items = items or ["2.02,9.01"] * n
    return {
        "filings": {
            "recent": {
                "form": forms,
                "accessionNumber": accessions,
                "filingDate": ["2024-01-30"] * n,
                "acceptanceDateTime": ["2024-01-30T16:05:12.000"] * n,
                "primaryDocument": ["ex99-1.htm"] * n,
                "items": items,
            }
        }
    }


class SequencedHandler:
    """Return scripted responses per URL; supports status sequences for retries."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self._seq: dict[str, list[httpx.Response]] = {}
        self._default: dict[str, httpx.Response] = {}

    def set(self, url: str, response: httpx.Response) -> None:
        self._default[url] = response

    def set_sequence(self, url: str, responses: list[httpx.Response]) -> None:
        self._seq[url] = list(responses)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.calls.append(url)
        if url in self._seq and self._seq[url]:
            return self._seq[url].pop(0)
        if url in self._default:
            return self._default[url]
        return httpx.Response(404, text=f"missing mock for {url}")


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(
        GUIDANCE_WATCH_DB_PATH=tmp_path / "t.db",
        GUIDANCE_WATCH_CACHE_DIR=tmp_path / "cache",
        GUIDANCE_WATCH_REPORTS_DIR=tmp_path / "reports",
        SEC_USER_AGENT="GuidanceWatchTest/0.1 (test@example.com)",
        SEC_REQUESTS_PER_SECOND=1000.0,
        OPENROUTER_API_KEY="",
    )


@pytest.mark.integration
def test_retry_on_503_then_success(settings: Settings) -> None:
    conn = init_db(settings.db_path)
    cache = ResponseCache(settings.cache_dir, conn)
    handler = SequencedHandler()
    url = "https://example.test/retry"
    handler.set_sequence(
        url,
        [
            httpx.Response(503, text="busy"),
            httpx.Response(200, content=b'{"ok": true}'),
        ],
    )
    sleeps: list[float] = []
    client = SecClient(
        user_agent=settings.sec_user_agent,
        cache=cache,
        requests_per_second=1000.0,
        transport=httpx.MockTransport(handler),
        sleep=sleeps.append,
        base_backoff_s=0.01,
    )
    status, body, from_cache = client.get_bytes(url, use_cache=False)
    assert status == 200
    assert json.loads(body)["ok"] is True
    assert from_cache is False
    assert client.stats.retries == 1
    assert sleeps  # backoff invoked


@pytest.mark.integration
def test_retry_on_429_uses_backoff(settings: Settings) -> None:
    conn = init_db(settings.db_path)
    cache = ResponseCache(settings.cache_dir, conn)
    handler = SequencedHandler()
    url = "https://example.test/rate"
    handler.set_sequence(
        url,
        [
            httpx.Response(429, headers={"Retry-After": "0.01"}, text="slow down"),
            httpx.Response(200, content=b"ok"),
        ],
    )
    sleeps: list[float] = []
    client = SecClient(
        user_agent=settings.sec_user_agent,
        cache=cache,
        requests_per_second=1000.0,
        transport=httpx.MockTransport(handler),
        sleep=sleeps.append,
    )
    status, body, _ = client.get_bytes(url, use_cache=False)
    assert status == 200
    assert body == b"ok"
    assert client.stats.retries == 1
    assert 0.01 in sleeps


@pytest.mark.integration
def test_cache_hit_skips_network(settings: Settings) -> None:
    conn = init_db(settings.db_path)
    cache = ResponseCache(settings.cache_dir, conn)
    handler = SequencedHandler()
    url = "https://example.test/cached"
    handler.set(url, httpx.Response(200, content=b"payload"))
    client = SecClient(
        user_agent=settings.sec_user_agent,
        cache=cache,
        requests_per_second=1000.0,
        transport=httpx.MockTransport(handler),
        sleep=lambda _s: None,
    )
    client.get_bytes(url)
    client.get_bytes(url)
    assert handler.calls.count(url) == 1
    assert client.stats.cache_hits == 1


@pytest.mark.integration
def test_bootstrap_cursor_then_unchanged_feed_zero_work(settings: Settings) -> None:
    conn = init_db(settings.db_path)
    cache = ResponseCache(settings.cache_dir, conn)
    handler = SequencedHandler()
    url = submissions_url(AMD.cik)
    payload = _submissions(accessions=["0000002488-24-000003", "0000002488-24-000002"])
    handler.set(url, httpx.Response(200, content=json.dumps(payload).encode()))
    client = SecClient(
        user_agent=settings.sec_user_agent,
        cache=cache,
        requests_per_second=1000.0,
        transport=httpx.MockTransport(handler),
        sleep=lambda _s: None,
    )

    first = poll_watchlist(client, conn, companies=(AMD,))
    assert first.detected == []
    acc, _ = get_cursor(conn, AMD.cik)
    assert acc == "0000002488-24-000003"

    second = poll_watchlist(client, conn, companies=(AMD,))
    assert second.detected == []
    assert second.skipped_duplicate == 0


@pytest.mark.integration
def test_new_filing_detected_then_duplicate_skipped(settings: Settings, tmp_path: Path) -> None:
    conn = init_db(settings.db_path)
    cache = ResponseCache(settings.cache_dir, conn)
    handler = SequencedHandler()
    url = submissions_url(AMD.cik)

    bootstrap = _submissions(accessions=["0000002488-24-000001"])
    handler.set(url, httpx.Response(200, content=json.dumps(bootstrap).encode()))
    client = SecClient(
        user_agent=settings.sec_user_agent,
        cache=cache,
        requests_per_second=1000.0,
        transport=httpx.MockTransport(handler),
        sleep=lambda _s: None,
    )
    poll_watchlist(client, conn, companies=(AMD,))

    # Newer filing appears at head of recent feed
    updated = _submissions(accessions=["0000002488-24-000100", "0000002488-24-000001"])
    handler.set(url, httpx.Response(200, content=json.dumps(updated).encode()))
    # Bust cache for submissions URL
    conn.execute("DELETE FROM http_cache")
    conn.commit()

    detected = poll_watchlist(client, conn, companies=(AMD,))
    assert len(detected.detected) == 1
    assert detected.detected[0].metadata.accession == "0000002488-24-000100"

    # Same feed again — cursor already at newest → unchanged feed, zero work
    conn.execute("DELETE FROM http_cache")
    conn.commit()
    again = poll_watchlist(client, conn, companies=(AMD,))
    assert again.detected == []
    assert again.skipped_duplicate == 0

    # If cursor is behind an accession that was already analyzed, skip it.
    fixtures = Path(__file__).resolve().parents[1] / "fixtures"
    analyze_accession("0000002488-24-000100", fixtures_root=fixtures, settings=settings)
    conn.execute(
        "UPDATE filing_cursors SET last_accession = ? WHERE cik = ?",
        ("0000002488-24-000001", AMD.cik),
    )
    conn.execute("DELETE FROM http_cache")
    conn.commit()
    skipped = poll_watchlist(client, conn, companies=(AMD,))
    assert skipped.detected == []
    assert skipped.skipped_duplicate == 1


@pytest.mark.integration
def test_non_retryable_404_raises(settings: Settings) -> None:
    conn = init_db(settings.db_path)
    cache = ResponseCache(settings.cache_dir, conn)
    handler = SequencedHandler()
    url = "https://example.test/missing"
    handler.set(url, httpx.Response(404, text="nope"))
    client = SecClient(
        user_agent=settings.sec_user_agent,
        cache=cache,
        requests_per_second=1000.0,
        transport=httpx.MockTransport(handler),
        sleep=lambda _s: None,
    )
    with pytest.raises(SecHttpError) as exc:
        client.get_bytes(url, use_cache=False)
    assert exc.value.status_code == 404
