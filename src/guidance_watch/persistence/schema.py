"""SQLite schema bootstrap."""

from __future__ import annotations

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS companies (
    cik TEXT PRIMARY KEY,
    ticker TEXT NOT NULL UNIQUE,
    name TEXT,
    fiscal_year_end_month INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS filing_cursors (
    cik TEXT PRIMARY KEY REFERENCES companies(cik),
    last_accession TEXT,
    last_accepted_at TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS filings (
    accession TEXT PRIMARY KEY,
    cik TEXT NOT NULL REFERENCES companies(cik),
    ticker TEXT,
    form TEXT NOT NULL,
    filing_date TEXT NOT NULL,
    accepted_at TEXT NOT NULL,
    primary_document TEXT,
    items_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS filing_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    accession TEXT NOT NULL REFERENCES filings(accession),
    filename TEXT NOT NULL,
    description TEXT,
    document_type TEXT,
    is_html INTEGER NOT NULL DEFAULT 0,
    content_hash TEXT,
    cache_path TEXT,
    UNIQUE (accession, filename)
);

CREATE TABLE IF NOT EXISTS guidance_claims (
    claim_id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    cik TEXT NOT NULL,
    accession TEXT NOT NULL REFERENCES filings(accession),
    filing_date TEXT NOT NULL,
    accepted_at TEXT NOT NULL,
    source_document TEXT NOT NULL,
    target_fiscal_period TEXT NOT NULL,
    metric TEXT NOT NULL,
    gaap_or_non_gaap TEXT NOT NULL,
    lower_bound_usd_m REAL NOT NULL,
    upper_bound_usd_m REAL NOT NULL,
    currency TEXT NOT NULL,
    unit_in_source TEXT NOT NULL,
    is_revision INTEGER NOT NULL DEFAULT 0,
    revision_direction TEXT NOT NULL,
    supporting_quote TEXT NOT NULL,
    confidence REAL NOT NULL,
    needs_review INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (accession, source_document, target_fiscal_period, lower_bound_usd_m, upper_bound_usd_m)
);

CREATE TABLE IF NOT EXISTS actual_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cik TEXT NOT NULL,
    target_fiscal_period TEXT NOT NULL,
    actual_revenue_usd_m REAL NOT NULL,
    actual_publication_date TEXT NOT NULL,
    source TEXT,
    UNIQUE (cik, target_fiscal_period, actual_publication_date)
);

CREATE TABLE IF NOT EXISTS guidance_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guidance_claim_id TEXT NOT NULL REFERENCES guidance_claims(claim_id),
    target_fiscal_period TEXT NOT NULL,
    original_lower_usd_m REAL NOT NULL,
    original_upper_usd_m REAL NOT NULL,
    latest_lower_usd_m REAL NOT NULL,
    latest_upper_usd_m REAL NOT NULL,
    actual_revenue_usd_m REAL NOT NULL,
    actual_publication_date TEXT NOT NULL,
    revision_count INTEGER NOT NULL DEFAULT 0,
    downward_revision_occurred INTEGER NOT NULL DEFAULT 0,
    source_documents_json TEXT,
    UNIQUE (guidance_claim_id)
);

CREATE TABLE IF NOT EXISTS sentiment_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    accession TEXT,
    claim_id TEXT,
    model_name TEXT NOT NULL,
    model_revision TEXT NOT NULL,
    positive_probability REAL NOT NULL,
    neutral_probability REAL NOT NULL,
    negative_probability REAL NOT NULL,
    tone_score REAL NOT NULL,
    analyzed_text_hash TEXT NOT NULL,
    analyzed_text TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS analysis_runs (
    run_id TEXT PRIMARY KEY,
    accession TEXT NOT NULL REFERENCES filings(accession),
    ticker TEXT,
    cik TEXT,
    status TEXT NOT NULL,
    ignore_reason TEXT,
    prompt_version TEXT,
    agent_version TEXT,
    scoring_version TEXT,
    model_identifier TEXT,
    assessment_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (accession)
);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES analysis_runs(run_id),
    accession TEXT NOT NULL,
    format TEXT NOT NULL,
    path TEXT,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (run_id, format)
);

CREATE TABLE IF NOT EXISTS job_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    accession TEXT NOT NULL,
    status TEXT NOT NULL,
    detail TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS evaluation_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    passed INTEGER NOT NULL,
    detail TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS http_cache (
    cache_key TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    status_code INTEGER,
    content_hash TEXT NOT NULL,
    path TEXT NOT NULL,
    fetched_at TEXT NOT NULL
);
"""
