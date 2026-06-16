"""Rich console output formatting for CLI mode.

Provides utilities for rendering agent output with colors,
tables, panels, progress indicators, and markdown.
"""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

# ── Theme ────────────────────────────────────────────────────────────

OPSAGENTS_THEME = Theme(
    {
        "agent.name": "bold cyan",
        "agent.task": "italic",
        "status.running": "bold yellow",
        "status.success": "bold green",
        "status.error": "bold red",
        "status.pending": "dim",
        "risk.low": "green",
        "risk.medium": "yellow",
        "risk.high": "red",
        "risk.critical": "bold red",
        "info": "dim cyan",
        "heading": "bold magenta",
    }
)

console = Console(theme=OPSAGENTS_THEME)


# ── Banner ───────────────────────────────────────────────────────────

BANNER = r"""
  ___              _                    _
 / _ \ _ __  ___  / \   __ _  ___ _ __ | |_ ___
| | | | '_ \/ __|| _ \ / _` |/ _ \ '_ \| __/ __|
| |_| | |_) \__ \/ ___ \ (_| |  __/ | | | |_\__ \
 \___/| .__/|___/_/   \_\__, |\___|_| |_|\__|___/
      |_|               |___/
"""


def print_banner() -> None:
    """Print the OpsAgents ASCII banner."""
    console.print(Text(BANNER, style="bold cyan"))
    console.print("  [dim]Cloud & DevOps AI Agents • v0.1.0[/dim]\n")


# ── Agent Output ─────────────────────────────────────────────────────


def print_agent_header(agent_name: str, task: str) -> None:
    """Print an agent invocation header."""
    panel = Panel(
        f"[agent.task]{task}[/agent.task]",
        title=f"[agent.name]🤖 {agent_name}[/agent.name]",
        title_align="left",
        border_style="cyan",
        padding=(1, 2),
    )
    console.print(panel)


def print_status(message: str, status: str = "running") -> None:
    """Print a status message with appropriate styling."""
    icons = {
        "running": "⏳",
        "success": "✅",
        "error": "❌",
        "pending": "⏸️",
        "info": "ℹ️",  # noqa: RUF001
        "warning": "⚠️",
    }
    icon = icons.get(status, "•")
    style = f"status.{status}" if f"status.{status}" in OPSAGENTS_THEME.styles else "info"
    console.print(f"  {icon} [{style}]{message}[/{style}]")


def print_action_plan(actions: list[dict[str, Any]]) -> None:
    """Print a formatted action plan table."""
    table = Table(
        title="📋 Action Plan",
        title_style="heading",
        show_lines=True,
        border_style="dim",
    )
    table.add_column("#", style="bold", width=4)
    table.add_column("Action", style="cyan")
    table.add_column("Resource", style="yellow")
    table.add_column("Risk", width=10)

    for i, action in enumerate(actions, 1):
        risk = action.get("risk_level", "medium")
        risk_style = f"risk.{risk}"
        table.add_row(
            str(i),
            action.get("action", "Unknown"),
            action.get("resource", "-"),
            Text(risk.upper(), style=risk_style),
        )

    console.print()
    console.print(table)
    console.print()


def print_results(results: list[dict[str, Any]]) -> None:
    """Print action results in a formatted table."""
    table = Table(
        title="📊 Results",
        title_style="heading",
        show_lines=True,
        border_style="dim",
    )
    table.add_column("Action", style="cyan")
    table.add_column("Status", width=10)
    table.add_column("Output")

    for result in results:
        status = "✅" if result.get("success") else "❌"
        table.add_row(
            result.get("action", "Unknown"),
            status,
            result.get("output", result.get("error", "-"))[:100],
        )

    console.print()
    console.print(table)
    console.print()


def print_report(report: str) -> None:
    """Print a markdown-formatted final report."""
    panel = Panel(
        Markdown(report),
        title="[heading]📝 Report[/heading]",
        title_align="left",
        border_style="magenta",
        padding=(1, 2),
    )
    console.print()
    console.print(panel)


def create_spinner(message: str = "Working...") -> Progress:
    """Create a Rich spinner progress indicator."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    )


def print_error(message: str, detail: str = "") -> None:
    """Print an error message."""
    console.print(f"\n  ❌ [status.error]{message}[/status.error]")
    if detail:
        console.print(f"     [dim]{detail}[/dim]")


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"\n  ✅ [status.success]{message}[/status.success]")
