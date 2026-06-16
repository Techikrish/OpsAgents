"""Incident Response Agent.

Monitors CloudWatch, analyzes logs, performs root cause analysis,
and executes remediation runbooks with human approval.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from opsagents.cloud.incident.prompts import ROOT_CAUSE_PROMPT, SYSTEM_PROMPT
from opsagents.cloud.incident.tools import get_incident_tools
from opsagents.core.base_agent import BaseAgent
from opsagents.core.state import ActionResult, AgentState

logger = logging.getLogger(__name__)


class IncidentAgent(BaseAgent):
    """Incident Response Agent."""

    @property
    def name(self) -> str:
        return "Incident Response"

    @property
    def description(self) -> str:
        return (
            "Monitors CloudWatch alarms, analyzes logs, performs root cause "
            "analysis, and suggests/executes remediation runbooks."
        )

    @property
    def system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def get_tools(self) -> list[Any]:
        return get_incident_tools()

    def analyze(self, state: AgentState) -> dict[str, Any]:
        """Analyze the incident and gather initial data."""
        task = state["task"]
        analysis = self.invoke_llm(
            f"Analyze this incident/task and determine:\n"
            f"1. Severity assessment (SEV1-SEV4)\n"
            f"2. What data to collect (alarms, logs, metrics, changes)\n"
            f"3. Initial hypothesis\n\nTask: {task}"
        )
        return {
            "context": {"analysis": analysis, "task_type": self._classify_task(task)},
            "messages": [HumanMessage(content=task), AIMessage(content=analysis)],
        }

    def create_plan(self, state: AgentState) -> dict[str, Any]:
        """Create an incident response plan."""
        task_type = state.get("context", {}).get("task_type", "investigate")
        actions = []

        if task_type in ("investigate", "full"):
            actions.extend([
                {"action": "Check active alarms", "resource": "CloudWatch", "risk_level": "low", "type": "alarms"},
                {"action": "Analyze recent changes", "resource": "CloudTrail", "risk_level": "low", "type": "changes"},
            ])

        if task_type in ("logs", "investigate", "full"):
            actions.append(
                {"action": "Query error logs", "resource": "CloudWatch Logs", "risk_level": "low", "type": "logs"}
            )

        if task_type in ("metrics", "investigate", "full"):
            actions.append(
                {"action": "Analyze metrics", "resource": "CloudWatch Metrics", "risk_level": "low", "type": "metrics"}
            )

        actions.append(
            {"action": "Root cause analysis", "resource": "All gathered data", "risk_level": "low", "type": "rca"}
        )

        if task_type == "postmortem":
            actions.append(
                {"action": "Generate post-mortem", "resource": "Incident report", "risk_level": "low", "type": "postmortem"}
            )

        return {"action_plan": actions}

    def execute_action(self, state: AgentState, action: dict[str, Any]) -> ActionResult:
        """Execute an incident response action."""
        action_type = action.get("type", "")
        region = self.config.aws.region
        profile = self.config.aws.profile

        from opsagents.cloud.incident.tools import (
            analyze_metrics,
            get_active_alarms,
            get_recent_changes,
            query_logs,
        )

        try:
            if action_type == "alarms":
                result = get_active_alarms.invoke({"profile": profile, "region": region})
                return ActionResult(success=True, action=action["action"], output=str(result))

            elif action_type == "changes":
                result = get_recent_changes.invoke({"hours": 24, "profile": profile, "region": region})
                return ActionResult(success=True, action=action["action"], output=str(result))

            elif action_type == "logs":
                # Try common log groups
                log_groups = ["/aws/lambda", "/ecs", "/aws/apigateway"]
                all_results = []
                for lg in log_groups:
                    try:
                        result = query_logs.invoke({"log_group": lg, "hours": 1, "profile": profile, "region": region})
                        all_results.append(str(result))
                    except Exception:
                        continue
                output = "\n".join(all_results) if all_results else "No log results found."
                return ActionResult(success=True, action=action["action"], output=output)

            elif action_type == "metrics":
                result = analyze_metrics.invoke({
                    "namespace": "AWS/EC2", "metric_name": "CPUUtilization",
                    "hours": 3, "profile": profile, "region": region,
                })
                return ActionResult(success=True, action=action["action"], output=str(result))

            elif action_type == "rca":
                results = state.get("results", [])
                all_data = "\n\n".join(r.output for r in results if r.success)
                rca = self.invoke_llm(
                    ROOT_CAUSE_PROMPT.format(
                        alarms="See data below", logs="See data below",
                        metrics="See data below", changes="See data below",
                    ) + f"\n\nCollected Data:\n{all_data[:4000]}"
                )
                return ActionResult(success=True, action="Root cause analysis", output=rca)

            elif action_type == "postmortem":
                results = state.get("results", [])
                rca_result = next((r for r in results if "root cause" in r.action.lower()), None)
                rca_text = rca_result.output if rca_result else "Root cause pending investigation."
                from opsagents.cloud.incident.tools import generate_postmortem
                result = generate_postmortem.invoke({
                    "incident_summary": state["task"],
                    "root_cause": rca_text[:500],
                    "actions_taken": "Automated investigation via OpsAgents",
                })
                return ActionResult(success=True, action="Generate post-mortem", output=str(result))

        except Exception as e:
            return ActionResult(success=False, action=action["action"], error=str(e))

        return ActionResult(success=False, action=action["action"], error="Unknown action type")

    def _classify_task(self, task: str) -> str:
        """Classify incident task type."""
        task_lower = task.lower()
        if "postmortem" in task_lower or "post-mortem" in task_lower:
            return "postmortem"
        elif "log" in task_lower:
            return "logs"
        elif "metric" in task_lower or "cpu" in task_lower or "memory" in task_lower:
            return "metrics"
        return "investigate"
