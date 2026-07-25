"""Filing document models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class FilingMetadata(BaseModel):
    accession: str
    cik: str
    ticker: str | None = None
    form: str
    filing_date: str
    accepted_at: datetime
    primary_document: str | None = None
    items: list[str] = Field(default_factory=list)


class FilingDocument(BaseModel):
    accession: str
    filename: str
    description: str | None = None
    document_type: str | None = None
    is_html: bool = False


class FilingContent(BaseModel):
    accession: str
    filename: str
    content_type: str
    text: str
    retrieved_at: datetime | None = None
