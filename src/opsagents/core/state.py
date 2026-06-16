"""Shared LangGraph state definitions for all agents.

Every agent uses a common state schema to ensure consistent behavior
across the human-in-the-loop approval lifecycle.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any

from langchain_core.messages import AnyMessage  # noqa: TC002
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

# ── Risk Levels ──────────────────────────────────────────────────────


class RiskLevel(StrEnum):
    """Risk classification for agent actions.

    Determines the approval policy applied to each action.
    """

    LOW = "low"  # Read-only: list, describe, scan
    MEDIUM = "medium"  # Modifications: create, update, scale
    HIGH = "high"  # Destructive: delete, terminate
    CRITICAL = "critical"  # Irreversible: production deploy, destroy infra


# ── Approval Request ─────────────────────────────────────────────────


class ApprovalRequest(BaseModel):
    """A structured request for human approval before executing an action."""

    action: str = Field(description="Short description of the action to perform")
    risk_level: RiskLevel = Field(description="Risk classification")
    details: str = Field(description="Detailed explanation of what will happen")
    resource: str = Field(default="", description="Target resource identifier")
    estimated_impact: str = Field(default="", description="Expected impact description")
    rollback_plan: str = Field(default="", description="How to undo this action")
    options: list[str] = Field(
        default_factory=lambda: ["approve", "deny", "modify"],
        description="Available response options",
    )


# ── Action Result ────────────────────────────────────────────────────


class ActionResult(BaseModel):
    """Result of an executed agent action."""

    success: bool = Field(description="Whether the action succeeded")
    action: str = Field(description="Action that was performed")
    output: str = Field(default="", description="Action output / result data")
    error: str = Field(default="", description="Error message if failed")
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── Agent State ──────────────────────────────────────────────────────


class AgentState(TypedDict):
    """Shared state schema for all OpsAgents LangGraph graphs.

    Attributes:
        messages: Conversation history (LangGraph message accumulator).
        task: The user's natural language task description.
        context: Gathered context (resource info, scan results, etc.).
        action_plan: List of planned actions before execution.
        current_approval: Pending approval request (if any).
        approval_response: Human's response to the approval request.
        results: List of completed action results.
        final_report: Generated summary/report for the user.
        metadata: Arbitrary key-value metadata.
    """

    messages: Annotated[list[AnyMessage], add_messages]
    task: str
    context: dict[str, Any]
    action_plan: list[dict[str, Any]]
    current_approval: ApprovalRequest | None
    approval_response: str | None
    results: list[ActionResult]
    final_report: str
    metadata: dict[str, Any]


def create_initial_state(task: str) -> AgentState:
    """Create an initial blank state for an agent invocation.

    Args:
        task: The user's natural language task description.

    Returns:
        A fresh AgentState ready for graph execution.
    """
    return AgentState(
        messages=[],
        task=task,
        context={},
        action_plan=[],
        current_approval=None,
        approval_response=None,
        results=[],
        final_report="",
        metadata={},
    )
