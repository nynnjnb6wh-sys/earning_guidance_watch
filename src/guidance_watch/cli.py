"""CLI entrypoint for guidance-watch."""

from __future__ import annotations

import typer

from guidance_watch import __version__

app = typer.Typer(
    name="guidance-watch",
    help="EDGAR Earnings-Guidance Watch Agent (research MVP).",
    no_args_is_help=True,
    add_completion=False,
)


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
    accession: str = typer.Option(..., "--accession", help="SEC accession number."),
) -> None:
    """Analyze a single filing by accession number."""
    _ = accession
    typer.echo("analyze: not implemented yet (Slice 2).", err=True)
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
