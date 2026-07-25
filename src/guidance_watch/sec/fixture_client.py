"""Local fixture SEC client for offline analyze/eval runs."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from guidance_watch.models import FilingContent, FilingDocument, FilingMetadata
from guidance_watch.sec.html_text import html_to_text


class FixtureSecClient:
    """Reads filing metadata and HTML documents from a fixtures directory.

    Expected layout for an accession (dashes kept in directory name)::

        fixtures/filings/{accession}/metadata.json
        fixtures/filings/{accession}/documents/{filename}
    """

    def __init__(self, fixtures_root: Path) -> None:
        self.fixtures_root = fixtures_root
        # Support either tests/fixtures/filings/{accession} or data/edgar_raw/{TICKER}/{accession}
        nested = fixtures_root / "filings"
        self.filings_root = nested if nested.is_dir() else fixtures_root

    def _accession_dir(self, accession: str) -> Path:
        direct = self.filings_root / accession
        if direct.is_dir():
            return direct
        # Nested ticker layout used by data/edgar_raw downloads.
        if self.filings_root.is_dir():
            for child in self.filings_root.iterdir():
                candidate = child / accession
                if candidate.is_dir():
                    return candidate
        raise FileNotFoundError(f"No fixture filing for accession {accession}")

    def get_filing_metadata(self, accession: str) -> FilingMetadata:
        raw = json.loads((self._accession_dir(accession) / "metadata.json").read_text())
        accepted = raw["accepted_at"]
        if isinstance(accepted, str):
            accepted_at = datetime.fromisoformat(accepted.replace("Z", "+00:00"))
        else:
            accepted_at = accepted
        return FilingMetadata(
            accession=raw["accession"],
            cik=raw["cik"],
            ticker=raw.get("ticker"),
            form=raw["form"],
            filing_date=raw["filing_date"],
            accepted_at=accepted_at,
            primary_document=raw.get("primary_document"),
            items=list(raw.get("items", [])),
        )

    def list_filing_documents(self, accession: str) -> list[FilingDocument]:
        meta_path = self._accession_dir(accession) / "documents.json"
        if meta_path.exists():
            docs = json.loads(meta_path.read_text())
            return [FilingDocument(**d) for d in docs]
        docs_dir = self._accession_dir(accession) / "documents"
        result: list[FilingDocument] = []
        for path in sorted(docs_dir.iterdir()):
            if path.is_file():
                result.append(
                    FilingDocument(
                        accession=accession,
                        filename=path.name,
                        description=None,
                        document_type=None,
                        is_html=path.suffix.lower() in {".htm", ".html"},
                    )
                )
        return result

    def fetch_filing_document(self, accession: str, filename: str) -> FilingContent:
        path = self._accession_dir(accession) / "documents" / filename
        if not path.is_file():
            raise FileNotFoundError(f"Missing document {filename} for {accession}")
        raw = path.read_text(encoding="utf-8", errors="replace")
        text = html_to_text(raw) if path.suffix.lower() in {".htm", ".html"} else raw
        return FilingContent(
            accession=accession,
            filename=filename,
            content_type="text/html" if path.suffix.lower() in {".htm", ".html"} else "text/plain",
            text=text,
        )
