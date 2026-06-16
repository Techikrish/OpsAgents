"""Human-in-the-loop approval system.

Provides approval handlers for both CLI (interactive terminal prompts)
and MCP (structured approval requests returned to coding agents).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

from opsagents.core.state import ApprovalRequest, RiskLevel

if TYPE_CHECKING:
    from opsagents.config import ApprovalConfig

logger = logging.getLogger(__name__)
console = Console()

# ── Risk Level Styling ───────────────────────────────────────────────

_RISK_STYLES = {
    RiskLevel.LOW: ("green", "✓", "LOW RISK"),
    RiskLevel.MEDIUM: ("yellow", "⚠", "MEDIUM RISK"),
    RiskLevel.HIGH: ("red", "⚠", "HIGH RISK"),
    RiskLevel.CRITICAL: ("bold red", "🛑", "CRITICAL RISK"),
}


# ── Abstract Handler ─────────────────────────────────────────────────


class ApprovalHandler(ABC):
    """Base class for approval handlers."""

    def __init__(self, config: ApprovalConfig) -> None:
        self.config = config

    def should_auto_approve(self, request: ApprovalRequest) -> bool:
        """Check if the action should be auto-approved based on policy."""
        risk = request.risk_level
        policy = getattr(self.config.risk_levels, risk.value, self.config.default_policy)
        return policy == "auto"

    @abstractmethod
    def request_approval(self, request: ApprovalRequest) -> str:
        """Request approval from the human.

        Args:
            request: The structured approval request.

        Returns:
            One of: "approve", "deny", "modify", or custom response.
        """
        ...

    def process(self, request: ApprovalRequest) -> tuple[bool, str]:
        """Process an approval request with policy check.

        Args:
            request: The approval request to process.

        Returns:
            Tuple of (approved: bool, response: str).
        """
        if self.should_auto_approve(request):
            logger.info(
                "Auto-approved action (risk=%s): %s",
                request.risk_level.value,
                request.action,
            )
            return True, "auto-approved"

        response = self.request_approval(request)
        approved = response.lower() in ("approve", "yes", "y")

        logger.info(
            "Approval %s for action '%s' (risk=%s): %s",
            "granted" if approved else "denied",
            request.action,
            request.risk_level.value,
            response,
        )

        return approved, response


# ── CLI Approval Handler ─────────────────────────────────────────────


class CLIApprovalHandler(ApprovalHandler):
    """Interactive terminal approval handler using Rich formatting."""

    def request_approval(self, request: ApprovalRequest) -> str:
        """Display a rich approval prompt in the terminal."""
        color, icon, label = _RISK_STYLES.get(
            request.risk_level, ("white", "?", "UNKNOWN")
        )

        # Build the approval panel
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Key", style="bold cyan", width=18)
        table.add_column("Value")

        table.add_row("Action", request.action)
        table.add_row("Risk Level", Text(f"{icon} {label}", style=color))
        table.add_row("Details", request.details)

        if request.resource:
            table.add_row("Resource", request.resource)
        if request.estimated_impact:
            table.add_row("Impact", request.estimated_impact)
        if request.rollback_plan:
            table.add_row("Rollback", request.rollback_plan)

        panel = Panel(
            table,
            title="[bold]🔐 Approval Required[/bold]",
            title_align="left",
            border_style=color,
            padding=(1, 2),
        )
        console.print()
        console.print(panel)

        # For critical actions, require typed confirmation
        if request.risk_level == RiskLevel.CRITICAL:
            console.print(
                f"\n[bold {color}]This is a CRITICAL action. "
                f'Type "CONFIRM" to proceed:[/bold {color}]'
            )
            response = Prompt.ask("  Confirmation")
            if response.strip().upper() == "CONFIRM":
                return "approve"
            return "deny"

        # Standard approve/deny prompt
        approved = Confirm.ask(
            f"\n  [{color}]Do you approve this action?[/{color}]",
            default=False,
        )
        return "approve" if approved else "deny"


# ── MCP Approval Handler ────────────────────────────────────────────


class MCPApprovalHandler(ApprovalHandler):
    """Approval handler for MCP mode — returns structured requests.

    When running as an MCP server, approvals are returned as structured
    data to the calling coding agent (e.g., Claude Code, Cursor),
    which then presents the approval request to the human user.
    """

    def __init__(self, config: ApprovalConfig) -> None:
        super().__init__(config)
        self._pending_response: str | None = None

    def set_response(self, response: str) -> None:
        """Set the approval response (called by MCP server after human responds)."""
        self._pending_response = response

    def request_approval(self, request: ApprovalRequest) -> str:
        """Return a structured approval request for the coding agent."""
        if self._pending_response is not None:
            response = self._pending_response
            self._pending_response = None
            return response

        # In MCP mode, we raise an interrupt that the graph handles
        # The approval request data is returned to the calling agent
        raise ApprovalInterrupt(request)

    def to_mcp_response(self, request: ApprovalRequest) -> dict[str, Any]:
        """Convert an approval request to MCP-friendly format."""
        _color_name, icon, label = _RISK_STYLES.get(
            request.risk_level, ("white", "?", "UNKNOWN")
        )
        return {
            "type": "approval_required",
            "action": request.action,
            "risk_level": request.risk_level.value,
            "risk_label": f"{icon} {label}",
            "details": request.details,
            "resource": request.resource,
            "estimated_impact": request.estimated_impact,
            "rollback_plan": request.rollback_plan,
            "options": request.options,
            "message": (
                f"{icon} Approval Required: {request.action}\n\n"
                f"Risk: {label}\n"
                f"Details: {request.details}\n"
                + (f"Resource: {request.resource}\n" if request.resource else "")
                + (f"Impact: {request.estimated_impact}\n" if request.estimated_impact else "")
                + "\nPlease respond with: approve, deny, or modify"
            ),
        }


# ── Approval Interrupt ───────────────────────────────────────────────


class ApprovalInterrupt(Exception):  # noqa: N818
    """Raised when an MCP approval is needed.

    Used by LangGraph's interrupt mechanism to pause graph execution
    and return the approval request to the calling agent.
    """

    def __init__(self, request: ApprovalRequest) -> None:
        self.request = request
        super().__init__(f"Approval required: {request.action}")


# ── Factory ──────────────────────────────────────────────────────────


def create_approval_handler(
    config: ApprovalConfig,
    mode: str = "cli",
) -> ApprovalHandler:
    """Create an approval handler for the given mode.

    Args:
        config: Approval configuration.
        mode: "cli" for interactive terminal, "mcp" for MCP server mode.

    Returns:
        An ApprovalHandler instance.
    """
    if mode == "mcp":
        return MCPApprovalHandler(config)
    return CLIApprovalHandler(config)
