# EDGAR Earnings-Guidance Watch Agent

Research MVP that monitors a small watchlist of US-listed companies for new SEC Form 8-K filings and produces an evidence-backed assessment when a filing contains numerical quarterly GAAP revenue guidance.

This is a research and agent-observability project, **not an investment product**. It does not claim to detect deception or predict stock performance.

See [`mvp_implementation_plan.md`](mvp_implementation_plan.md) for scope, formulas, acceptance criteria, and the sliced execution plan.

## Status

Slices **0–8** implemented for the MVP offline path:

- Deterministic scoring, fixture analyze, SEC poller/cache, tool-calling agent (scripted default), FinBERT interface, backfill + curated actuals, OpenTelemetry, eval harness

**No OpenRouter key required** for the default path (ScriptedProvider + deterministic extractor + FakeSentiment).

## Setup

```bash
# Python 3.12+
uv sync --extra dev
# optional: uv sync --extra finbert   # real FinBERT weights
# optional: uv sync --extra phoenix  # local trace viewer deps
cp .env.example .env
```

Set a descriptive `SEC_USER_AGENT` in `.env` before live EDGAR calls.

## Commands

```bash
guidance-watch --help
guidance-watch watch --once
guidance-watch watch --interval 900
guidance-watch analyze --accession ACCESSION --fixtures tests/fixtures
guidance-watch backfill --ticker AMD --quarters 8
guidance-watch eval
```

### Local EDGAR downloads (untracked)

```bash
python scripts/download_edgar_sample.py   # → data/edgar_raw/ (gitignored)
guidance-watch analyze --accession 0001045810-26-000051 --fixtures data/edgar_raw
guidance-watch backfill --ticker NVDA --fixtures data/edgar_raw --actuals seed/actuals.csv
```

## Verification

```bash
uv sync --extra dev
ruff check .
ruff format --check .
mypy src
pytest -m "not live" -q
guidance-watch eval
```

Live checks (network / credentials / FinBERT weights) are optional and marked `@pytest.mark.live`.

## Telemetry / Phoenix

By default spans export to the console.

```bash
# optional local Phoenix
phoenix serve
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:6006/v1/traces
guidance-watch analyze --accession 0000002488-24-000100 --fixtures tests/fixtures

# disable tracing processors
export GUIDANCE_WATCH_OTEL=off
```

API keys are redacted from span attributes.

## Configuration

| Variable | Purpose |
|---|---|
| `SEC_USER_AGENT` | Required descriptive EDGAR User-Agent |
| `OPENROUTER_API_KEY` | Optional; enables live LLM via OpenRouter |
| `OPENROUTER_MODEL` | Default `openai/gpt-4.1-nano` |
| `GUIDANCE_WATCH_DB_PATH` | SQLite path |
| `GUIDANCE_WATCH_CACHE_DIR` | HTTP/filing cache |
| `GUIDANCE_WATCH_REPORTS_DIR` | JSON/Markdown reports |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Optional Phoenix/OTLP |

## Known limitations

- US-listed Form 8-K HTML only (no PDF/OCR, no IR site scraping)
- Quarterly GAAP revenue ranges only (no EPS/full-year as primary metric)
- Revision linking is best-effort; ambiguous links → `needs_review` (no synthetic revision eval fixtures)
- Actuals come from curated `seed/actuals.csv` in the MVP (XBRL later)
- Heuristic reliability score is not a probability the current guide is correct
- Default analyze path uses a deterministic extractor; OpenRouter agent is optional

## License

MIT
