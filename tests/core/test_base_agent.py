"""Test base agent functionality."""

from __future__ import annotations

from typing import Any
import pytest

from opsagents.core.base_agent import BaseAgent
from opsagents.core.state import ActionResult, AgentState
from opsagents.config import OpsAgentsConfig


class DummyAgent(BaseAgent):
    """Minimal agent for base testing."""

    @property
    def name(self) -> str:
        return "Test Dummy"

    @property
    def description(self) -> str:
        return "A dummy agent for tests."

    @property
    def system_prompt(self) -> str:
        return "You are a test dummy."

    def get_tools(self) -> list[Any]:
        return []

    def analyze(self, state: AgentState) -> dict[str, Any]:
        return {"context": {"analyzed": True}}

    def create_plan(self, state: AgentState) -> dict[str, Any]:
        return {
            "action_plan": [
                {
                    "action": "Do dummy work",
                    "resource": "Dummy",
                    "risk_level": "low",
                    "type": "dummy_action",
                }
            ]
        }

    def execute_action(self, state: AgentState, action: dict[str, Any]) -> ActionResult:
        return ActionResult(
            success=True,
            action=action["action"],
            output="Dummy success output",
        )


def test_base_agent_lifecycle(mock_config: OpsAgentsConfig, mock_llm: Any) -> None:
    """Verify that the standard agent execution flow runs to completion."""
    agent = DummyAgent(config=mock_config, mode="cli")
    
    state = agent.run("Perform a dummy task")
    
    assert state["task"] == "Perform a dummy task"
    assert state["context"]["analyzed"] is True
    assert len(state["action_plan"]) == 1
    assert state["action_plan"][0]["action"] == "Do dummy work"
    assert len(state["results"]) == 1
    assert state["results"][0].success is True
    assert "final_report" in state
    assert "Do dummy work" in state["final_report"]
