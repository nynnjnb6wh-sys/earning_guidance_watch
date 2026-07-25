# EDGAR Earnings-Guidance Watch Agent

Research MVP that monitors a small watchlist of US-listed companies for new SEC Form 8-K filings and produces an evidence-backed assessment when a filing contains numerical quarterly GAAP revenue guidance.

This is a research and agent-observability project, not an investment product. It does not claim to detect deception or predict stock performance.

See [`mvp_implementation_plan.md`](mvp_implementation_plan.md) for scope, formulas, acceptance criteria, and the sliced execution plan.

## Status

Slices 0–2 complete (skeleton, models/scoring, fixture analyze → persisted reports). **No OpenRouter key required** for the default path: ScriptedProvider + deterministic extractor. OpenRouter (default model `openai/gpt-4.1-nano`) is optional for later live agent runs.

## Setup

```bash
# Python 3.12+
uv sync --all-extras
# or: pip install -e ".[dev]"
cp .env.example .env
```

## Commands

```bash
guidance-watch --help
guidance-watch watch --once
guidance-watch watch --interval 900
guidance-watch analyze --accession ACCESSION
guidance-watch backfill --ticker AMD --quarters 8
guidance-watch eval
```

## Verification

```bash
uv sync --all-extras
ruff check .
ruff format --check .
mypy src
pytest -m "not live" -q
```

Live checks (network + credentials) are optional and marked `@pytest.mark.live`.

## Configuration

Copy `.env.example` to `.env`. Set a descriptive `SEC_USER_AGENT`.

LLM modes:

- **Default (no key):** scripted / deterministic extraction — sufficient for offline tests, fixtures, and local `analyze`.
- **Optional live:** set `OPENROUTER_API_KEY`. Default model is `openai/gpt-4.1-nano`. OpenRouter `:free` models still need a key; they are unbilled, not keyless.

## License

MIT
