"""Fetch filing index + HTML documents via SecClient into a local layout."""

from __future__ import annotations

import json
import re
from pathlib import Path

from guidance_watch.models import FilingContent, FilingDocument, FilingMetadata
from guidance_watch.sec.client import SecClient, filing_document_url, filing_index_url
from guidance_watch.sec.html_text import html_to_text


def _keep_html_name(name: str, primary: str | None) -> bool:
    lower = name.lower()
    if not lower.endswith((".htm", ".html")):
        return False
    if "-index" in lower or re.fullmatch(r"r\d+\.htm", lower):
        return False
    if primary and name == primary:
        return True
    return any(
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


def materialize_filing(
    client: SecClient,
    meta: FilingMetadata,
    dest_root: Path,
) -> Path:
    """Download index + selected HTML docs under dest_root/{accession}/."""
    acc_dir = dest_root / meta.accession
    docs_dir = acc_dir / "documents"
    docs_dir.mkdir(parents=True, exist_ok=True)
    (acc_dir / "metadata.json").write_text(
        json.dumps(
            {
                "accession": meta.accession,
                "cik": meta.cik,
                "ticker": meta.ticker,
                "form": meta.form,
                "filing_date": meta.filing_date,
                "accepted_at": meta.accepted_at.isoformat(),
                "primary_document": meta.primary_document,
                "items": meta.items,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    index = client.get_json(filing_index_url(meta.cik, meta.accession))
    (acc_dir / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    items = index.get("directory", {}).get("item", [])
    if isinstance(items, dict):
        items = [items]
    doc_meta: list[dict[str, object]] = []
    for item in items:
        name = item.get("name") or ""
        if not _keep_html_name(str(name), meta.primary_document):
            continue
        url = filing_document_url(meta.cik, meta.accession, str(name))
        status, body, _ = client.get_bytes(url)
        if status != 200:
            continue
        (docs_dir / str(name)).write_bytes(body)
        doc_meta.append(
            {
                "accession": meta.accession,
                "filename": name,
                "description": item.get("type"),
                "document_type": item.get("type"),
                "is_html": True,
            }
        )
    (acc_dir / "documents.json").write_text(json.dumps(doc_meta, indent=2), encoding="utf-8")
    return acc_dir


class LiveFilingStore:
    """Thin adapter exposing fixture-client-like reads over materialized filings."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def get_filing_metadata(self, accession: str) -> FilingMetadata:
        from guidance_watch.sec.fixture_client import FixtureSecClient

        return FixtureSecClient(self.root).get_filing_metadata(accession)

    def list_filing_documents(self, accession: str) -> list[FilingDocument]:
        from guidance_watch.sec.fixture_client import FixtureSecClient

        return FixtureSecClient(self.root).list_filing_documents(accession)

    def fetch_filing_document(self, accession: str, filename: str) -> FilingContent:
        from guidance_watch.sec.fixture_client import FixtureSecClient

        content = FixtureSecClient(self.root).fetch_filing_document(accession, filename)
        # Ensure text extracted
        if content.content_type.startswith("text/html") and "<" in content.text[:200]:
            content.text = html_to_text(content.text)
        return content
