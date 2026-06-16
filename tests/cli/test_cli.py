"""Tests for the Click CLI."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from opsagents.cli import cli


def test_cli_version() -> None:
    """Verify that 'opsagents version' returns the correct version string."""
    runner = CliRunner()
    result = runner.invoke(cli, ["version"])
    assert result.exit_code == 0
    assert "OpsAgents v" in result.output


def test_cli_help() -> None:
    """Verify that help outputs show all expected commands."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    
    expected_commands = [
        "infra",
        "security",
        "cost",
        "incident",
        "architect",
        "cicd",
        "k8s",
        "monitor",
        "gitops",
        "container",
        "mcp",
        "version",
    ]
    
    for cmd in expected_commands:
        assert cmd in result.output
