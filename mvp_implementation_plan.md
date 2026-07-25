# EDGAR Earnings-Guidance Watch Agent — MVP Implementation Plan

**Status:** draft — actionable, but several decisions in [§4 Open questions](#4-open-questions) should be confirmed before Slice 3 (agent extraction) and Slice 4 (historical metrics). Every open question has a proposed default so an agent can proceed unblocked if no answer arrives.

**Document version:** 0.5
**Settled since 0.1:** revision end-to-end eval demoted (D17) — no synthetic revision fixtures.
**Settled since 0.2:** LLM provider is OpenRouter (D18).
**Settled since 0.3:** default model `openai/gpt-4.1-nano` (O2 / D18).
**Settled since 0.4:** no OpenRouter key for now (D19 / O1 deferred) — default to ScriptedProvider + deterministic extractor.
**Scoring version:** `score-v1`
**Prompt version:** `extract-v1`
**Agent version:** `agent-v1`

---

## 0. How to use this document

This file serves two purposes:

1. **As-is brief.** Hand [§1 Agent brief](#1-agent-brief-use-as-is) to a single implementation agent. It is self-contained and includes objective, scope, schemas, formulas, acceptance criteria and reporting requirements.
2. **Sliced loop.** Feed [§2 Sliced execution plan](#2-sliced-execution-plan) one slice at a time in an agentic loop. Each slice has a goal, deliverables, a `done-when` gate and a verification command. Always include §1 as context plus [§3 Decisions register](#3-decisions-register) so the agent does not re-litigate settled choices.

Rules for either mode of use:

- Do not expand scope beyond this MVP without explicit approval.
- If a decision is required and not covered here, record it in §3 with a one-line rationale rather than leaving it implicit.
- Ambiguous data is marked `needs_review`, never guessed.

---

## 1. Agent brief (use as-is)

You are an implementation-focused software engineering agent. Build the following MVP end to end. Do not merely produce an architecture proposal: inspect the repository, implement the system, add tests and fixtures, run the verification suite, and document how to operate it.

### Project

EDGAR Earnings-Guidance Watch Agent

### Objective

Build a small agentic system that monitors selected US-listed companies for new SEC filings and automatically produces an evidence-backed assessment when a filing contains numerical quarterly revenue guidance.

The system answers:

> How accurate, directionally biased and stable has this management team's quarterly revenue guidance historically been, and is the tone of the new guidance unusual relative to its previous guidance releases?

This is a research and agent-observability project, not an investment product. Do not claim to detect deception or predict future stock performance.

### Product behavior

A user maintains a watchlist of two or three companies, initially semiconductor companies such as AMD, Intel and NVIDIA.

When a new EDGAR filing appears:

1. A deterministic poller detects the new accession number.
2. It filters for Form 8-K filings, initially Items 2.02 and 7.01.
3. An LLM agent inspects the filing and its HTML attachments.
4. The agent decides whether the filing contains numerical quarterly GAAP revenue guidance.
5. If relevant, the agent extracts the guidance and supporting evidence.
6. Deterministic code retrieves the company's usable historical records and calculates accuracy, bias and revision metrics.
7. FinBERT analyses the guidance/outlook language.
8. The system generates and persists a cited JSON and Markdown report.
9. The complete execution is traced and evaluated.

The watcher should support scheduled polling, but a `--once` mode is sufficient for local development and tests. Do not build push notifications or a graphical interface.

### Technology choices

Use Python 3.12 unless the repository already establishes another compatible version.

Prefer a minimal stack:

- Pydantic for typed models and validation
- httpx for SEC requests
- SQLite for persistence
- BeautifulSoup for HTML extraction
- Hugging Face Transformers with `ProsusAI/finbert`
- An LLM API with structured output/tool calling
- OpenTelemetry/OpenInference-compatible tracing
- Phoenix as the optional local trace viewer
- Pytest for testing

Keep the LLM provider behind a small interface so tests can use scripted or mocked responses. Do not require API credentials to run the deterministic test suite.

Follow existing repository conventions when they conflict with these choices.

### Strict MVP boundary

Support only:

- US-listed companies
- Two or three configured tickers
- Form 8-K
- HTML filings and HTML Exhibit 99.x attachments
- Numerical quarterly GAAP revenue ranges
- Eight previous completed fiscal quarters when available
- USD values normalized to millions
- Outlook/guidance-section sentiment
- Explicitly identifiable revisions when they appear in real filings (best-effort linking only; see D17)
- Local execution and persistence

Do not implement:

- Markets outside the US
- PDF or OCR processing
- Investor-relations website scraping
- Full-year guidance
- Profit, EPS, margin or cash-flow guidance
- Stock-price prediction
- Deception or lie detection
- A trained prediction model
- Multiple cooperating agents
- Kafka, distributed queues or production cloud infrastructure
- Fully automatic linking of ambiguous revisions
- Synthetic revision fixtures or an end-to-end eval path for revisions (D17)

Ambiguous records should be marked for review rather than guessed.

### SEC access requirements

Use EDGAR company-submissions data to discover filings and filing archives to retrieve filing documents and attachments.

Implement:

- A descriptive, configurable SEC User-Agent
- Conservative request pacing well below 10 requests per second
- Retries with exponential backoff for transient failures
- Local response caching
- Accession-number deduplication
- Accepted/publication timestamps
- Clear error reporting

The poller should store the last processed accession for each company. Reprocessing the same accession must not produce duplicate analyses.

### Agent boundary

Keep discovery and calculations deterministic. Use the LLM only where document interpretation is valuable.

The agent should receive a candidate filing and have typed tools resembling:

```python
get_filing_metadata(accession: str) -> FilingMetadata
list_filing_documents(accession: str) -> list[FilingDocument]
fetch_filing_document(accession: str, filename: str) -> FilingContent
get_company_history(cik: str, before: datetime) -> list[GuidanceOutcome]
analyze_sentiment(text: str) -> SentimentResult
calculate_assessment(input: AssessmentInput) -> ReliabilityAssessment
```

The agent must:

1. Inspect filing metadata and available documents.
2. Select the most likely earnings-release attachment.
3. Determine whether it contains relevant guidance.
4. Extract the guidance into the required schema.
5. Provide exact supporting excerpts and document identifiers.
6. Call the history, sentiment and calculation tools when relevant.
7. Return a schema-valid result with uncertainty and review flags.

Do not allow the LLM to calculate scores, signed errors or aggregates.

### Core data models

Implement typed models equivalent to the following.

**Guidance claim**

```
ticker
cik
accession
filing_date
accepted_at
source_document
target_fiscal_period
metric
gaap_or_non_gaap
lower_bound_usd_m
upper_bound_usd_m
currency
unit_in_source
is_revision
revision_direction: upward | downward | unchanged | unknown
supporting_quote
confidence
needs_review
```

Require:

- `metric == "revenue"`
- `gaap_or_non_gaap == "gaap"`
- A quarterly target period
- Both numerical bounds
- A supporting quote that appears in the retrieved source

Reject or flag claims that fail validation.

**Historical outcome**

```
guidance_claim_id
target_fiscal_period
original_lower_usd_m
original_upper_usd_m
latest_lower_usd_m
latest_upper_usd_m
actual_revenue_usd_m
actual_publication_date
revision_count
downward_revision_occurred
source_documents
```

**Sentiment result**

```
model_name
model_revision
positive_probability
neutral_probability
negative_probability
tone_score
analyzed_text_hash
```

Define:

```
tone_score = positive_probability - negative_probability
```

Persist the exact outlook text or its content-addressed cached representation so runs are reproducible.

### Historical calculations

For each completed historical quarter, calculate the original-guidance figures:

```
midpoint = (lower_bound + upper_bound) / 2
signed_error_pct = 100 * (actual_revenue - midpoint) / midpoint
absolute_error_pct = abs(signed_error_pct)
inside_range = lower_bound <= actual_revenue <= upper_bound
```

Interpret signed error as:

- Positive: actual revenue exceeded the midpoint; guidance was conservative.
- Negative: actual revenue fell below the midpoint; guidance was optimistic.
- Near zero: guidance was well centred.

Calculate and report:

- Number of usable historical quarters
- Original-guidance range hit rate
- Latest-guidance range hit rate, when revisions exist
- Median signed error
- Mean absolute error
- Revision frequency
- Downward-revision frequency
- Current tone score
- Median historical tone score
- Current tone anomaly

Use original guidance as the primary measure. Do not let a later revision overwrite it.

Bias is a separate descriptive dimension and must not be treated as the inverse of reliability. Label the observed tendency as:

- `conservative` when median signed error is greater than +1%
- `optimistic` when it is less than −1%
- `approximately centered` otherwise

Call this an "observed historical tendency," especially when fewer than eight quarters are available.

### Heuristic reliability assessment

Preserve component scores in the output:

```
historical_hit_score = 100 * original_range_hit_rate
revision_score = 100 * (1 - downward_revision_quarters / usable_quarters)
tone_consistency_score = clip(100 - 50 * abs(current_tone - historical_median_tone), 0, 100)
total_score = 0.60 * historical_hit_score
            + 0.25 * revision_score
            + 0.15 * tone_consistency_score
```

Map the total to:

- 75–100: `high`
- 50–74.999: `medium`
- 0–49.999: `low`

Call it a heuristic historical-reliability score, not a probability that the current guidance is correct.

If fewer than four completed historical quarters are available, return `insufficient_history` instead of a high/medium/low label. Still show the available descriptive statistics.

If the sentiment baseline is unavailable, return the sentiment component as `unavailable` and clearly record that the overall score was not calculated. Do not silently impute missing data.

### Temporal-safety rule

The analysis cutoff is the new filing's `accepted_at` timestamp.

The agent may use only information published on or before that cutoff. Historical actuals are usable only when their publication date precedes the cutoff.

Later information may be used by the evaluation harness as ground truth, but never as agent input.

Add a deterministic guard that rejects tool results dated after the cutoff. Record temporal-leakage attempts as evaluation failures and trace events.

### Reports

For each relevant filing, produce:

1. A machine-readable JSON report.
2. A concise Markdown report.

The report should include:

- Current revenue guidance range and target quarter
- Source filing, accession and document
- Historical sample size
- Original and latest range hit rates
- Median signed error and bias label
- Mean absolute error
- Revision and downward-revision counts
- Current and historical tone
- Tone anomaly
- Component scores and total score, when calculable
- Reliability label
- Limitations, missing data and review flags
- Supporting citations for every numerical claim

Citations may be SEC filing URLs plus short supporting excerpts. Never invent a citation or present an unsupported number.

### Persistence

Use SQLite tables for at least:

- companies/watchlist
- filing cursors
- filings
- filing documents/cache metadata
- guidance claims
- actual results
- guidance outcomes
- sentiment results
- analysis runs
- reports
- job attempts/status
- evaluation results

Job statuses should include:

```
detected
ignored
running
completed
failed
needs_review
```

Store prompt version, model identifier, agent version and scoring-version identifiers with each analysis.

### CLI

Provide commands equivalent to:

```
guidance-watch watch --once
guidance-watch watch --interval 900
guidance-watch analyze --accession ACCESSION
guidance-watch backfill --ticker AMD --quarters 8
guidance-watch eval
```

`backfill` should run the same retrieval and extraction pipeline over historical filings. It may produce `needs_review` records when linking guidance, revisions or actual results is ambiguous.

### Telemetry

Treat each processed filing as one trace with spans for:

```
poll
detect
filter
retrieve metadata
retrieve document
classify
extract guidance
load history
sentiment inference
calculate assessment
render report
persist result
```

Record at least:

- Ticker, CIK and accession
- Cutoff timestamp
- Retrieved document names
- Tool names, arguments and status
- Cache hits
- SEC response codes
- Retries
- Extracted fields
- Validation failures
- FinBERT model and revision
- Prompt, agent and scoring versions
- LLM model
- Tokens, latency and estimated cost when available
- Tool-call count
- Final job status
- Evaluation results and failure category

Avoid recording API keys or unrelated sensitive environment data.

Provide sensible no-op or console tracing when Phoenix is not running. Document how to connect an optional local Phoenix instance.

### Evaluation suite

Create a small fixture-based evaluation dataset. The deterministic suite must run without live SEC or LLM access.

Cover at least these cases:

1. Relevant 8-K with one HTML Exhibit 99 and one quarterly revenue range.
2. Irrelevant 8-K with no guidance.
3. Several Exhibit 99 documents where only one is relevant.
4. Quarterly and full-year guidance in the same release.
5. Fiscal quarter differing from the calendar quarter.
6. Units expressed as billions and millions.
7. Actual revenue just inside or outside a range.
8. A post-cutoff document that must be rejected.
9. Duplicate accession processing.
10. Temporary HTTP failure followed by a successful retry.
11. Missing sentiment baseline.
12. Too little history for a reliability label.
13. A supporting quote that does not appear in the source.

**Revision coverage (demoted — D17):** do not invent synthetic revision Exhibit 99 fixtures, and do not require an end-to-end agent path for explicit or ambiguous revisions. Keep the data model fields (`is_revision`, `revision_direction`, revision counts) and the deterministic linker. Unit-test the linker only: when a second claim shares a `target_fiscal_period`, never overwrite original guidance; when linking is not explicitly identifiable, emit `needs_review`. Treat revision linking as best-effort in the MVP; real mid-quarter 8-K revisions for the watchlist issuers are rare and out of scope for fixture construction.

Measure:

- Filing classification precision/recall on fixtures
- Correct attachment selection
- Guidance extraction accuracy by field
- Correct unit normalization
- Revision-linker unit correctness (no overwrite of original; ambiguous → `needs_review`) — not end-to-end revision extraction accuracy
- Temporal-safety violations
- Supporting-quote validation
- Required-tool use
- Duplicate-run rate
- Schema validity
- Deterministic score correctness
- Trace/span completeness
- End-to-end success
- Tool calls, retries and latency

Include a few manually verified historical events if practical, but keep live-network tests separate and optional.

### Acceptance criteria

The MVP is complete when:

- A configured company can be polled for new 8-K filings.
- The same accession cannot be processed twice.
- The agent can select and inspect HTML attachments using typed tools.
- Relevant quarterly GAAP revenue guidance is extracted into a validated schema.
- Irrelevant filings are ignored with a recorded reason.
- Historical accuracy, bias and revision metrics are calculated deterministically.
- FinBERT sentiment and tone anomaly are included when sufficient history exists.
- Post-cutoff information is rejected.
- JSON and Markdown reports are persisted with source citations.
- Every end-to-end run emits the required trace structure.
- The fixture-based suite runs without network access or credentials.
- The project includes setup instructions, configuration examples and commands for polling, backfilling, analysing and evaluating.
- Tests, formatting and static checks pass.

### Implementation approach

First inspect the repository and preserve its existing structure and conventions. Then:

1. Write a brief implementation checklist.
2. Implement the smallest vertical slice from fixture filing to persisted report.
3. Add SEC polling, caching and deduplication.
4. Add the tool-calling agent with mocked deterministic tests.
5. Add historical metrics and bias calculations.
6. Add FinBERT behind an interface.
7. Add traces and evaluators.
8. Run all verification commands and fix failures.
9. Update the README with exact commands and known limitations.

Prefer clear, replaceable modules over framework-heavy abstractions. Keep business calculations pure and extensively unit tested.

If an external dependency or credential prevents live verification, complete and verify the fixture-based implementation, clearly identify the blocked live check, and provide the exact command the user should run once the dependency is available.

At completion, report:

- What was implemented
- Important design decisions
- Files changed
- Verification commands and results
- Remaining limitations
- The next smallest useful improvement

Do not expand the scope beyond this MVP without explicit approval.

---

## 2. Sliced execution plan

Each slice is independently promptable. Include §1 and §3 as context. Do not start a slice until the previous slice's `done-when` gate passes.

### Slice 0 — Repository skeleton and toolchain

**Goal:** an installable, lint-clean, test-clean empty project.

Deliverables:

- `pyproject.toml` with the `guidance-watch` console script, runtime deps, and `dev` / `finbert` / `phoenix` / `live` optional-dependency groups.
- Package layout under `src/guidance_watch/`: `config.py`, `models/`, `sec/`, `agent/`, `analysis/`, `sentiment/`, `persistence/`, `reporting/`, `telemetry/`, `eval/`, `cli.py`.
- `tests/` with `unit/`, `integration/`, `eval/`, `fixtures/`; markers `unit`, `integration`, `eval`, `live` (with `live` deselected by default).
- Ruff + mypy configuration, `.env.example`, `README.md` stub, `.gitignore`.
- One smoke test asserting `guidance-watch --help` exits 0.

**Done when:** `ruff check . && ruff format --check . && mypy src && pytest -m "not live"` all pass on an empty implementation.

### Slice 1 — Typed models and pure calculations

**Goal:** the entire scoring core, with no I/O.

Deliverables:

- Pydantic models for `GuidanceClaim`, `HistoricalOutcome`, `SentimentResult`, `AssessmentInput`, `ReliabilityAssessment`, `FilingMetadata`, `FilingDocument`, `FilingContent`, plus a `FiscalPeriod` value type with parsing and ordering.
- `analysis/metrics.py`: midpoint, signed/absolute error, `inside_range`, hit rates, median signed error, mean absolute error, revision and downward-revision frequency.
- `analysis/scoring.py`: component scores, weighted total, label mapping, `insufficient_history` path, `unavailable` sentiment path (total is `None`, never imputed).
- `analysis/bias.py`: tendency label with the ±1% thresholds and the "observed historical tendency" wording.

**Done when:** unit tests cover boundary values exactly — total scores of 49.999 / 50 / 74.999 / 75, median signed error at exactly ±1%, actual revenue exactly on each bound, 3 vs 4 usable quarters, zero usable quarters, and missing sentiment.

### Slice 2 — Vertical slice: fixture filing to persisted report

**Goal:** the smallest end-to-end path, with a scripted LLM and a fake sentiment provider.

Deliverables:

- SQLite schema and migration bootstrap for all tables in §1, with unique constraints enforcing accession-level dedupe.
- HTML text extraction (BeautifulSoup) plus quote-verification helper (normalized whitespace, exact substring match against retrieved source text).
- JSON and Markdown renderers with a citation for every numeric claim.
- `guidance-watch analyze --accession …` running against a local fixture SEC client.

**Done when:** running `analyze` on eval case 1 writes a guidance claim, an analysis run, and both report artifacts; re-running the same accession produces no second analysis and exits with a clear "already processed" status.

### Slice 3 — SEC client, poller, cache, dedupe

Deliverables:

- `sec/client.py`: httpx client, configurable descriptive User-Agent, token-bucket pacing, exponential backoff with jitter on 429/5xx/timeouts, structured error reporting.
- Content-addressed response cache on disk with metadata rows in SQLite; cache hits recorded on spans.
- `sec/poller.py`: submissions feed, form filter `8-K`, item filter `2.02` / `7.01`, per-company cursor persistence, accepted/publication timestamp parsing normalized to UTC.
- `guidance-watch watch --once` and `--interval N`.

**Done when:** integration tests using a mock transport cover a transient 503 followed by success, a 429 with backoff, an unchanged feed producing zero work, and a duplicate accession being skipped. No test touches the network.

### Slice 4 — Tool-calling agent

Deliverables:

- `agent/tools.py`: the six typed tools, each wrapped by the temporal guard.
- `agent/provider.py`: minimal LLM interface (`complete_with_tools`) plus a `ScriptedProvider` for tests and one real provider implementation.
- `agent/runner.py`: bounded tool-call loop, classification then extraction, schema validation, review flagging, prompt/agent version stamping.
- `agent/prompts/extract-v1.md`.

**Done when:** deterministic tests with scripted transcripts pass for attachment selection among several Exhibit 99 files, rejection of an irrelevant filing with a recorded reason, rejection of a hallucinated quote, and rejection of a post-cutoff document. Required-tool-use is asserted.

### Slice 5 — Sentiment behind an interface

Deliverables:

- `sentiment/base.py` protocol; `FinBertProvider` (lazy model load, long-text chunking, recorded `model_name` and `model_revision`); `FakeSentimentProvider` returning fixed probabilities.
- Outlook/guidance section locator, content-addressed persistence of the analyzed text, `analyzed_text_hash`.
- Historical tone baseline assembled from stored sentiment of prior guidance releases; `unavailable` when the baseline is empty.

**Done when:** the default test suite never downloads model weights; a `live`-marked test exercises real FinBERT; tone anomaly and `tone_consistency_score` are covered by unit tests.

### Slice 6 — Backfill and actuals linking

Deliverables:

- `guidance-watch backfill --ticker AMD --quarters 8` reusing the same retrieval and extraction pipeline.
- Actuals ingestion per the decision in [Q4](#q4-source-of-actual-revenue-blocking).
- Guidance-to-actual linking with explicit `needs_review` on ambiguity; no guessing.
- Revision linker as a best-effort unit (D17): no synthetic revision fixtures; ambiguous second claims for the same period become `needs_review`; original guidance is never overwritten.

**Done when:** fixture backfill produces outcomes for unambiguous quarters; unit tests assert that a second claim for the same period does not overwrite original guidance and that non-explicit links become `needs_review`; no end-to-end revision Exhibit 99 fixtures are required.

### Slice 7 — Telemetry

Deliverables:

- OpenTelemetry/OpenInference setup with console exporter by default, OTLP to Phoenix when configured, and a no-op path.
- One trace per processed filing with the exact span names in §1 and the required attributes.
- Redaction guard for secrets.

**Done when:** an in-memory span exporter test asserts span-name completeness and required attributes for one full run; an assertion confirms no environment secret values appear in span attributes.

### Slice 8 — Evaluation harness and docs

Deliverables:

- Fixture dataset covering the 13 end-to-end cases above (plus unit-only revision-linker tests per D17) with expected outputs and a separate later-information ground-truth file used only by the harness.
- `guidance-watch eval` producing the metric table in §1 and persisting `evaluation_results` rows with failure categories.
- README: setup, configuration, all CLI commands, optional Phoenix instructions, limitations, disclaimer.

**Done when:** `pytest -m "not live"` and `guidance-watch eval` both pass offline, and the completion report in §1 is produced.

---

## 3. Decisions register

Defaults an implementing agent should assume unless an open question is answered otherwise. Amend in place as decisions are confirmed.

| # | Area | Default decision |
|---|---|---|
| D1 | Python / packaging | Python 3.12, `uv` for env management with a plain `pyproject.toml` (pip-installable), src layout |
| D2 | Quality gates | ruff (lint + format), mypy strict on `src/`, pytest with `-m "not live"` default |
| D3 | Watchlist | AMD, INTC, NVDA; CIKs resolved once from EDGAR `company_tickers.json` and cached in the DB |
| D4 | Fiscal period format | Canonical `FY{year}Q{n}` as reported by the company, with the calendar end date stored alongside |
| D5 | Range from "± " guidance | `"$X billion, plus or minus 2%"` and `"$X ± $300 million"` normalize to explicit bounds; `unit_in_source` preserves the original wording |
| D6 | GAAP classification | Revenue is treated as GAAP unless the document explicitly labels it non-GAAP or adjusted; otherwise `needs_review` |
| D7 | Rate limiting | 4 requests/second ceiling with jitter, single-threaded polling |
| D8 | Storage paths | `./data/guidance_watch.db`, `./data/cache/`, `./reports/`; all overridable by config |
| D9 | Timezone | EDGAR timestamps parsed as US/Eastern, stored as UTC ISO-8601 |
| D10 | Amendments | `8-K/A` treated as a distinct accession and processed normally |
| D11 | Currency | Non-USD guidance is rejected with a recorded reason |
| D12 | Downward revision | Defined as a decrease in the range midpoint versus the prior claim for the same target period |
| D13 | Tone anomaly | `current_tone - historical_median_tone`, reported as a signed number; flagged as "unusual" when `abs(...) > 0.30` |
| D14 | FinBERT long text | Split into 512-token windows, average probabilities weighted by token count, record window count |
| D15 | Scheduling | `--interval` is an in-process sleep loop; no cron, systemd or external scheduler |
| D16 | Secrets | LLM key via env var only; never logged, never in spans, `.env.example` documents names without values |
| D17 | Revision eval coverage | **Settled:** demote. No synthetic revision fixtures. No end-to-end agent path required for explicit/ambiguous revisions. Keep schema + deterministic linker; unit-test no-overwrite and `needs_review` on ambiguous links only. Document as best-effort / often `needs_review` in README limitations. |
| D18 | LLM provider | **Settled:** OpenRouter. OpenAI-compatible client with `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL` defaulting to `https://openrouter.ai/api/v1`, and `OPENROUTER_MODEL` defaulting to `openai/gpt-4.1-nano`. Provider stays behind the small interface; deterministic suite uses `ScriptedProvider` and never requires the key. |
| D19 | No-key default | **Settled:** Owner will not provide an OpenRouter key for now. Default runtime mode is `scripted` (ScriptedProvider + deterministic Exhibit 99 extractor). OpenRouter `:free` models are not a keyless workaround — they still require `OPENROUTER_API_KEY`. Live OpenRouter remains optional and off until a key is supplied. |

---

## 4. Open questions

### Blocking (answer before Slice 3/4)

#### Q1: Where does this repository live?

**Settled:** https://github.com/nynnjnb6wh-sys/earning_guidance_watch (public). Implementation agents should be launched with this repo attached. Transfer or recreate under a different owner if needed.

#### Q2: LLM provider and model

**Settled (provider + model + key policy):** OpenRouter (D18) with default `OPENROUTER_MODEL=openai/gpt-4.1-nano` (O2). No key for now (D19): MVP proceeds on the scripted/deterministic path. Live OpenRouter client is implemented behind the interface but only activated when a key appears.

Still open:

- Should a per-run cost ceiling be enforced? (O3)

*Working assumption:* no live LLM test in the default suite.

#### Q3: Is a real network verification expected?

The deterministic suite runs offline by design. Do you also want `live`-marked tests that hit EDGAR and the real LLM, run manually?

*Proposed default:* yes, `live` tests exist but are deselected by default and documented with exact commands.

#### Q4: Source of actual revenue (blocking)

**Settled for MVP:** curated CSV seed at `seed/actuals.csv` (option C) with explicit `actual_publication_date` values. XBRL company-facts (A) remains a later enhancement; option B stays out of scope. Missing/ambiguous links → `needs_review`.

#### Q5: Fiscal calendars

NVIDIA's fiscal year is offset by roughly a year from the calendar; Intel and AMD are close to calendar. Should fiscal-year-end be hardcoded per ticker in config, or derived from filings?

*Proposed default:* per-ticker fiscal-year-end in the watchlist config, with a validation check that derived quarter end dates fall within a sane window of the filing date; mismatches become `needs_review`.

### Non-blocking (defaults are probably fine)

#### Q6: Sentiment-unavailable behavior

§1 says report the component as `unavailable` and record that the overall score was not calculated. Confirm this means `total_score = null` and `label = "unavailable"` (rather than reweighting the remaining 0.60/0.25 components to sum to 1.0).

*Proposed default:* `total_score = null`, component scores still shown, no reweighting.

#### Q7: Reliability label between 4 and 7 quarters

Below four quarters gives `insufficient_history`. For four to seven, do we emit a normal label plus a low-confidence caveat?

*Proposed default:* yes — normal label, `sample_size_caveat: true`, and the "observed historical tendency" wording in the report.

#### Q8: `revision_score` denominator

Confirm `downward_revision_quarters` counts distinct target quarters with at least one downward revision, divided by usable quarters.

*Proposed default:* as stated; quarters with no guidance revision at all count as non-downward.

#### Q9: Historical tone baseline construction

Median historical tone requires FinBERT over each prior guidance release's outlook text, which backfill must generate. Confirm backfill runs sentiment inference (this is the one place default-suite runs would want model weights, hence the fake provider).

*Proposed default:* backfill computes and stores sentiment; fixtures ship precomputed `SentimentResult` rows so tests stay offline.

#### Q10: Outlook-section boundaries

Sentiment should cover the outlook/guidance section, not the whole release. Should the section be located deterministically (heading regex such as "Outlook", "Guidance", "Financial Outlook") or should the agent return the span?

*Proposed default:* agent returns the span with document identifier and offsets; a deterministic heading-based fallback applies when the agent does not, and the chosen method is recorded on the span.

#### Q11: Report scope and location

One report pair per relevant filing, written to `./reports/{ticker}/{accession}.{json,md}` and also stored in SQLite?

*Proposed default:* yes, both — files for humans, rows for the eval harness.

#### Q12: CI

Should a GitHub Actions workflow run the offline gates on push?

*Proposed default:* yes, one workflow running ruff, mypy and `pytest -m "not live"` on Python 3.12.

---

## 5. Verification commands

```bash
uv sync --all-extras            # or: pip install -e ".[dev]"
ruff check .
ruff format --check .
mypy src
pytest -m "not live" -q
guidance-watch watch --once
guidance-watch eval
```

Optional, requires credentials or network:

```bash
pytest -m live -q              # real EDGAR + real LLM + real FinBERT
phoenix serve                  # then set OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:6006/v1/traces
```

---

## 6. Completion report template

At completion, report:

- **What was implemented** — per slice, with the acceptance criterion each satisfies.
- **Important design decisions** — including any amendments to §3 and answers adopted for §4.
- **Files changed** — grouped by module.
- **Verification commands and results** — exact commands and outcomes, including eval metric table.
- **Remaining limitations** — especially anything in the "Do not implement" list that a reader might expect to work, plus every `needs_review` category the system can emit.
- **The next smallest useful improvement** — one change, scoped.

---

## 7. Owner TODOs

Items the human owner must supply; implementation agents must not invent these.

| ID | Status | Action |
|---|---|---|
| O1 | **deferred** | No OpenRouter key for now (D19). MVP uses ScriptedProvider + deterministic extractor. A key can be added later to enable live agent extraction; `:free` models still need a key. |
| O2 | **done** | Default model set to `openai/gpt-4.1-nano` (economical tool-calling model for filing extraction). Override via `OPENROUTER_MODEL` if needed. |
| O3 | pending | Decide whether a per-run OpenRouter cost ceiling is required. |
