#!/usr/bin/env python3
"""Download recent Form 8-K filings + HTML Exhibit 99.x into data/edgar_raw/.

This directory is gitignored (under data/). No OpenRouter key required.
Uses a descriptive SEC User-Agent and conservative pacing.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "edgar_raw"
USER_AGENT = "GuidanceWatch/0.1 (research; oscarssilva@gmail.com)"
BASE = "https://data.sec.gov"
WWW = "https://www.sec.gov"
ARCHIVE = "https://www.sec.gov/Archives/edgar/data"

# Watchlist CIKs (zero-padded 10 digits for submissions API)
WATCHLIST = {
    "AMD": "0000002488",
    "INTC": "0000050863",
    "NVDA": "0001045810",
}

MAX_8K_PER_TICKER = 6
SLEEP_S = 0.35


def client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"},
        timeout=60.0,
        follow_redirects=True,
    )


def get_json(c: httpx.Client, url: str) -> dict:
    time.sleep(SLEEP_S)
    r = c.get(url)
    r.raise_for_status()
    return r.json()


def get_bytes(c: httpx.Client, url: str) -> tuple[int, bytes, str]:
    time.sleep(SLEEP_S)
    r = c.get(url)
    return r.status_code, r.content, r.headers.get("content-type", "")


def accession_nodash(acc: str) -> str:
    return acc.replace("-", "")


def download_ticker(c: httpx.Client, ticker: str, cik: str) -> list[str]:
    out_ticker = OUT / ticker
    out_ticker.mkdir(parents=True, exist_ok=True)
    subs_url = f"{BASE}/submissions/CIK{cik}.json"
    print(f"[{ticker}] fetching submissions {subs_url}")
    subs = get_json(c, subs_url)
    (out_ticker / "submissions.json").write_text(json.dumps(subs, indent=2), encoding="utf-8")

    recent = subs.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    filed = recent.get("filingDate", [])
    accepted = recent.get("acceptanceDateTime", [])
    primary = recent.get("primaryDocument", [])
    items = recent.get("items", [])

    selected: list[int] = []
    for i, form in enumerate(forms):
        if form in {"8-K", "8-K/A"}:
            # Prefer earnings-related items when present
            item = items[i] if i < len(items) else ""
            if "2.02" in item or "7.01" in item or not item:
                selected.append(i)
        if len(selected) >= MAX_8K_PER_TICKER:
            break

    saved: list[str] = []
    for i in selected:
        acc = accessions[i]
        acc_dir = out_ticker / acc
        acc_dir.mkdir(parents=True, exist_ok=True)
        docs_dir = acc_dir / "documents"
        docs_dir.mkdir(exist_ok=True)

        meta = {
            "ticker": ticker,
            "cik": cik,
            "accession": acc,
            "form": forms[i],
            "filing_date": filed[i],
            "accepted_at": accepted[i],
            "primary_document": primary[i],
            "items": [x.strip() for x in (items[i] or "").split(",") if x.strip()],
        }
        (acc_dir / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

        cik_num = str(int(cik))
        index_url = f"{ARCHIVE}/{cik_num}/{accession_nodash(acc)}/index.json"
        print(f"[{ticker}] {acc} index")
        status, body, _ = get_bytes(c, index_url)
        if status != 200:
            print(f"  ! index.json HTTP {status}")
            continue
        (acc_dir / "index.json").write_bytes(body)
        index = json.loads(body.decode("utf-8", errors="replace"))
        directory = index.get("directory", {})
        items_list = directory.get("item", [])

        doc_meta = []
        for item in items_list:
            name = item.get("name") or ""
            if not name:
                continue
            lower = name.lower()
            is_html = lower.endswith((".htm", ".html"))
            if not is_html:
                continue
            # Skip EDGAR index chrome and iXBRL R# stubs; keep exhibits/releases.
            if "-index" in lower or re.fullmatch(r"r\d+\.htm", lower):
                continue
            is_primary = name == primary[i]
            looks_exhibit = any(
                key in lower
                for key in (
                    "ex99",
                    "ex-99",
                    "exhibit",
                    "earnings",
                    "press",
                    "pr.htm",
                    "991",
                    "99-1",
                    "cfocommentary",
                    "outlook",
                )
            ) or lower.startswith("ex")
            if not (is_primary or looks_exhibit):
                continue
            file_url = f"{ARCHIVE}/{cik_num}/{accession_nodash(acc)}/{name}"
            print(f"  - {name}")
            st, content, ctype = get_bytes(c, file_url)
            if st != 200:
                print(f"    ! HTTP {st}")
                continue
            dest = docs_dir / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(content)
            doc_meta.append(
                {
                    "accession": acc,
                    "filename": name,
                    "description": item.get("type") or item.get("description"),
                    "document_type": item.get("type"),
                    "is_html": is_html,
                    "bytes": len(content),
                    "content_type": ctype,
                    "url": file_url,
                }
            )
        (acc_dir / "documents.json").write_text(json.dumps(doc_meta, indent=2), encoding="utf-8")
        saved.append(acc)
    return saved


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest: dict = {"user_agent": USER_AGENT, "tickers": {}}
    with client() as c:
        # tickers mapping (optional, useful)
        tickers_url = f"{WWW}/files/company_tickers.json"
        print(f"fetching {tickers_url}")
        st, body, _ = get_bytes(c, tickers_url)
        if st == 200:
            (OUT / "company_tickers.json").write_bytes(body)

        for ticker, cik in WATCHLIST.items():
            try:
                accessions = download_ticker(c, ticker, cik)
                manifest["tickers"][ticker] = {"cik": cik, "accessions": accessions}
            except Exception as exc:  # noqa: BLE001 — CLI sampler should continue
                manifest["tickers"][ticker] = {"cik": cik, "error": str(exc)}
                print(f"[{ticker}] ERROR: {exc}")

    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nDone. Files under {OUT} (gitignored via data/).")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
