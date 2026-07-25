"""SEC EDGAR client, polling, and caching."""

from guidance_watch.sec.client import SecClient
from guidance_watch.sec.fixture_client import FixtureSecClient
from guidance_watch.sec.html_text import html_to_text, quote_appears_in_source
from guidance_watch.sec.poller import poll_watchlist
from guidance_watch.sec.watchlist import DEFAULT_WATCHLIST

__all__ = [
    "DEFAULT_WATCHLIST",
    "FixtureSecClient",
    "SecClient",
    "html_to_text",
    "poll_watchlist",
    "quote_appears_in_source",
]
