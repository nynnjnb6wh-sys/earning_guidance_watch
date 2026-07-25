"""Slice 0 smoke tests for the CLI entrypoint."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from guidance_watch import __version__
from guidance_watch.cli import app

runner = CliRunner()


@pytest.mark.unit
def test_help_exits_zero() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "guidance-watch" in result.stdout.lower() or "EDGAR" in result.stdout


@pytest.mark.unit
def test_version_command() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


@pytest.mark.unit
def test_subcommand_help() -> None:
    for name in ("watch", "analyze", "backfill", "eval"):
        result = runner.invoke(app, [name, "--help"])
        assert result.exit_code == 0, name
