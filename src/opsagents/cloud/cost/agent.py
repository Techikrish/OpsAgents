"""Cost Optimizer Agent.

Analyzes AWS spending, identifies unused resources, recommends right-sizing,
and executes cost-saving actions with human approval.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from opsagents.cloud.cost.prompts import COST_ANALYSIS_PROMPT, SYSTEM_PROMPT
from opsagents.cloud.cost.tools import get_cost_tools
from opsagents.core.base_agent import BaseAgent
from opsagents.core.state import ActionResult, AgentState

logger = logging.getLogger(__name__)


class CostAgent(BaseAgent):
    """Cost Optimizer Agent."""

    @property
    def name(self) -> str:
        return "Cost Optimizer"

    @property
    def description(self) -> str:
        return (
            "Analyzes AWS spending, identifies unused resources, recommends "
            "right-sizing and reserved instances, and executes savings actions."
        )

    @property
    def system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def get_tools(self) -> list[Any]:
        return get_cost_tools()

    def analyze(self, state: AgentState) -> dict[str, Any]:
        """Analyze cost optimization task."""
        task = state["task"]
        analysis = self.invoke_llm(
            f"Analyze this cost optimization task:\n\n{task}\n\n"
            f"Determine:\n1. What cost data to collect\n2. What resources to check\n"
            f"3. What optimization strategies to explore"
        )
        return {
            "context": {"analysis": analysis, "task_type": self._classify_task(task)},
            "messages": [HumanMessage(content=task), AIMessage(content=analysis)],
        }

    def create_plan(self, state: AgentState) -> dict[str, Any]:
        """Create cost optimization plan."""
        task_type = state.get("context", {}).get("task_type", "analyze")
        actions = []

        if task_type in ("analyze", "full"):
            actions.append({
                "action": "Get cost breakdown",
                "resource": "AWS Cost Explorer",
                "risk_level": "low",
                "type": "cost_breakdown",
            })

        if task_type in ("unused", "full"):
            actions.append({
                "action": "Find unused resources",
                "resource": "EC2, EBS, EIP",
                "risk_level": "low",
                "type": "find_unused",
            })

        if task_type in ("rightsize", "full"):
            actions.append({
                "action": "Get right-sizing recommendations",
                "resource": "EC2 instances",
                "risk_level": "low",
                "type": "rightsizing",
            })

        if task_type in ("reserved", "full"):
            actions.append({
                "action": "Analyze Reserved Instances",
                "resource": "RI/Savings Plans",
                "risk_level": "low",
                "type": "reserved",
            })

        actions.append({
            "action": "Generate cost report",
            "resource": "All findings",
            "risk_level": "low",
            "type": "report",
        })

        return {"action_plan": actions}

    def execute_action(self, state: AgentState, action: dict[str, Any]) -> ActionResult:
        """Execute a cost optimization action."""
        action_type = action.get("type", "")
        region = self.config.aws.region
        profile = self.config.aws.profile

        from opsagents.cloud.cost.tools import (
            analyze_reserved_instances,
            find_unused_resources,
            get_cost_breakdown,
            recommend_rightsizing,
        )

        tool_map = {
            "cost_breakdown": lambda: get_cost_breakdown.invoke({"profile": profile, "region": region}),
            "find_unused": lambda: find_unused_resources.invoke({"profile": profile, "region": region}),
            "rightsizing": lambda: recommend_rightsizing.invoke({"profile": profile, "region": region}),
            "reserved": lambda: analyze_reserved_instances.invoke({"profile": profile, "region": region}),
        }

        if action_type in tool_map:
            try:
                result = tool_map[action_type]()
                return ActionResult(success=True, action=action["action"], output=str(result))
            except Exception as e:
                return ActionResult(success=False, action=action["action"], error=str(e))

        elif action_type == "report":
            results = state.get("results", [])
            all_data = "\n\n".join(r.output for r in results if r.success)
            report = self.invoke_llm(COST_ANALYSIS_PROMPT.format(cost_data=all_data))
            return ActionResult(success=True, action="Generate report", output=report)

        return ActionResult(success=False, action=action["action"], error="Unknown action")

    def _classify_task(self, task: str) -> str:
        """Classify cost task type."""
        task_lower = task.lower()
        if any(w in task_lower for w in ["unused", "idle", "waste", "clean"]):
            return "unused"
        elif any(w in task_lower for w in ["rightsize", "right-size", "resize", "optimize instance"]):
            return "rightsize"
        elif any(w in task_lower for w in ["reserved", "savings plan", "ri ", "commitment"]):
            return "reserved"
        elif any(w in task_lower for w in ["full", "all", "comprehensive", "complete"]):
            return "full"
        return "analyze"
