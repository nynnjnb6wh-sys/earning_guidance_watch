"""CLI entrypoint for guidance-watch."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from guidance_watch import __version__
from guidance_watch.config import get_settings
from guidance_watch.pipeline.analyze import analyze_accession

app = typer.Typer(
    name="guidance-watch",
    help="EDGAR Earnings-Guidance Watch Agent (research MVP).",
    no_args_is_help=True,
    add_completion=False,
)

_DEFAULT_FIXTURES = Path("tests/fixtures")


@app.callback()
def main() -> None:
    """Monitor EDGAR 8-K filings for quarterly GAAP revenue guidance."""


@app.command("version")
def version_cmd() -> None:
    """Print package version."""
    typer.echo(__version__)


@app.command("watch")
def watch(
    once: bool = typer.Option(False, "--once", help="Poll once and exit."),
    interval: int = typer.Option(900, "--interval", help="Seconds between polls."),
) -> None:
    """Poll watchlist companies for new Form 8-K filings."""
    _ = (once, interval)
    typer.echo("watch: not implemented yet (Slice 3).", err=True)
    raise typer.Exit(code=1)


@app.command("analyze")
def analyze(
    accession: Annotated[str, typer.Option("--accession", help="SEC accession number.")],
    fixtures: Annotated[
        Path,
        typer.Option(
            "--fixtures",
            help="Root directory containing offline filing fixtures.",
            exists=False,
            file_okay=False,
            dir_okay=True,
            readable=True,
        ),
    ] = _DEFAULT_FIXTURES,
) -> None:
    """Analyze a single filing by accession number (fixture client for offline use)."""
    settings = get_settings()
    result = analyze_accession(accession, fixtures_root=fixtures, settings=settings)
    if result.status == "already_processed":
        typer.echo(f"already processed: {accession} (run_id={result.run_id})")
        raise typer.Exit(code=0)
    if result.status == "ignored":
        typer.echo(f"ignored: {accession} ({result.detail or 'see analysis_runs'})")
        raise typer.Exit(code=0)
    if result.status == "completed":
        label = result.assessment.label.value if result.assessment else "n/a"
        typer.echo(f"completed: {accession} label={label} run_id={result.run_id}")
        raise typer.Exit(code=0)
    typer.echo(f"failed: {accession} status={result.status} detail={result.detail}", err=True)
    raise typer.Exit(code=1)


@app.command("backfill")
def backfill(
    ticker: str = typer.Option(..., "--ticker", help="Ticker symbol."),
    quarters: int = typer.Option(8, "--quarters", help="Number of fiscal quarters."),
) -> None:
    """Backfill historical guidance for a ticker."""
    _ = (ticker, quarters)
    typer.echo("backfill: not implemented yet (Slice 6).", err=True)
    raise typer.Exit(code=1)


@app.command("eval")
def eval_cmd() -> None:
    """Run the fixture-based evaluation suite."""
    typer.echo("eval: not implemented yet (Slice 8).", err=True)
    raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
