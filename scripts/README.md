# Scripts

## `download_edgar_sample.py`

Downloads recent Form 8-K filings (and HTML exhibits / press releases) for the
AMD / INTC / NVDA watchlist into **`data/edgar_raw/`**.

That directory is gitignored (`data/` in `.gitignore`) and is for local offline
work without an OpenRouter key.

```bash
uv sync --extra dev
python scripts/download_edgar_sample.py

# Analyze a downloaded accession (deterministic extractor; no LLM key):
guidance-watch analyze \
  --accession 0001045810-26-000051 \
  --fixtures data/edgar_raw
```
