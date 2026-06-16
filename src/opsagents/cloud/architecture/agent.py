"""Architecture Review Agent.

Evaluates AWS architecture against the AWS Well-Architected Framework,
discovers resources, generates diagrams, and produces review reports.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from opsagents.cloud.architecture.prompts import ARCHITECTURE_REVIEW_PROMPT, SYSTEM_PROMPT
from opsagents.cloud.architecture.tools import get_architecture_tools
from opsagents.core.base_agent import BaseAgent
from opsagents.core.state import ActionResult, AgentState

logger = logging.getLogger(__name__)


class ArchitectureAgent(BaseAgent):
    """Architecture Review Agent.

    Capabilities:
    - Inventory AWS resources
    - Check architecture reliability, performance, and security
    - Generate Mermaid architecture diagrams
    - Provide Well-Architected review reports
    """

    @property
    def name(self) -> str:
        return "Architecture Review"

    @property
    def description(self) -> str:
        return (
            "Reviews AWS architecture configurations, inventories resources, "
            "evaluates against the Well-Architected Framework, and generates reports."
        )

    @property
    def system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def get_tools(self) -> list[Any]:
        return get_architecture_tools()

    def analyze(self, state: AgentState) -> dict[str, Any]:
        """Analyze the architecture review task."""
        task = state["task"]
        analysis = self.invoke_llm(
            f"Analyze this architecture review task and determine what evaluations to run:\n\n{task}\n\n"
            f"Determine:\n1. AWS services of interest (e.g. ec2, s3, rds, lambda, ecs, elb)\n"
            f"2. Scope of review\n3. Key pillars of focus"
        )
        return {
            "context": {
                "analysis": analysis,
                "services": self._determine_services(task),
            },
            "messages": [HumanMessage(content=task), AIMessage(content=analysis)],
        }

    def create_plan(self, state: AgentState) -> dict[str, Any]:
        """Create an architecture review plan."""
        context = state.get("context", {})
        services = context.get("services", "ec2,s3,rds,lambda,ecs,elb")

        actions = [
            {
                "action": f"Discover AWS resources ({services})",
                "resource": "AWS inventory",
                "risk_level": "low",
                "type": "discover",
                "services": services,
            },
            {
                "action": "Check reliability controls",
                "resource": "Reliability configurations",
                "risk_level": "low",
                "type": "check_reliability",
            },
            {
                "action": "Check performance efficiency",
                "resource": "Performance configurations",
                "risk_level": "low",
                "type": "check_performance",
            },
            {
                "action": "Generate Mermaid architecture diagram",
                "resource": "Architecture visualization",
                "risk_level": "low",
                "type": "diagram",
            },
            {
                "action": "Generate Well-Architected review report",
                "resource": "Review findings",
                "risk_level": "low",
                "type": "report",
            }
        ]

        return {"action_plan": actions}

    def execute_action(self, state: AgentState, action: dict[str, Any]) -> ActionResult:
        """Execute an architecture review action."""
        action_type = action.get("type", "")
        region = self.config.aws.region
        profile = self.config.aws.profile

        from opsagents.cloud.architecture.tools import (
            check_performance,
            check_reliability,
            discover_resources,
            generate_architecture_diagram,
            generate_review_report,
        )

        if action_type == "discover":
            services = action.get("services", "ec2,s3,rds,lambda,ecs,elb")
            try:
                result = discover_resources.invoke({
                    "services": services,
                    "profile": profile,
                    "region": region,
                })
                return ActionResult(success=True, action=action["action"], output=str(result))
            except Exception as e:
                return ActionResult(success=False, action=action["action"], error=str(e))

        elif action_type == "check_reliability":
            try:
                result = check_reliability.invoke({
                    "profile": profile,
                    "region": region,
                })
                return ActionResult(success=True, action=action["action"], output=str(result))
            except Exception as e:
                return ActionResult(success=False, action=action["action"], error=str(e))

        elif action_type == "check_performance":
            try:
                result = check_performance.invoke({
                    "profile": profile,
                    "region": region,
                })
                return ActionResult(success=True, action=action["action"], output=str(result))
            except Exception as e:
                return ActionResult(success=False, action=action["action"], error=str(e))

        elif action_type == "diagram":
            results = state.get("results", [])
            resources_data = "{}"
            for r in results:
                if r.success and "discover_resources" in r.action:
                    try:
                        # Extract the json part from tool output
                        tool_out = json.loads(r.output)
                        resources_data = json.dumps(tool_out.get("result", {}).get("inventory", {}))
                    except Exception:
                        pass
                    break
            try:
                result = generate_architecture_diagram.invoke({
                    "resources": resources_data,
                    "description": state["task"]
                })
                return ActionResult(success=True, action=action["action"], output=str(result))
            except Exception as e:
                return ActionResult(success=False, action=action["action"], error=str(e))

        elif action_type == "report":
            results = state.get("results", [])
            resources_data = "{}"
            diagram_data = ""
            findings = []

            for r in results:
                if not r.success:
                    continue
                if "discover_resources" in r.action:
                    try:
                        tool_out = json.loads(r.output)
                        resources_data = json.dumps(tool_out.get("result", {}).get("inventory", {}))
                    except Exception:
                        pass
                elif "reliability" in r.action or "performance" in r.action:
                    try:
                        tool_out = json.loads(r.output)
                        findings.extend(tool_out.get("result", {}).get("findings", []))
                    except Exception:
                        pass
                elif "Mermaid" in r.action:
                    try:
                        tool_out = json.loads(r.output)
                        diagram_data = tool_out.get("result", {}).get("diagram", "")
                    except Exception:
                        pass

            findings_str = json.dumps(findings, indent=2)

            # Use LLM to analyze findings and write report
            report_text = self.invoke_llm(
                ARCHITECTURE_REVIEW_PROMPT.format(
                    resources=resources_data,
                    description=state["task"]
                ),
                context=f"Discovered Findings:\n{findings_str}"
            )

            try:
                # Format using review report tool
                result = generate_review_report.invoke({
                    "findings": findings_str,
                    "resources": resources_data,
                    "diagram": diagram_data
                })
                # We combine both LLM details and formatted report
                full_report = f"{report_text}\n\n{result}"
                return ActionResult(success=True, action=action["action"], output=full_report)
            except Exception as e:
                return ActionResult(success=False, action=action["action"], error=str(e))

        return ActionResult(success=False, action=action["action"], error="Unknown action type")

    def _determine_services(self, task: str) -> str:
        """Determine which services to discover based on task description."""
        task_lower = task.lower()
        services = []
        if "ec2" in task_lower or "compute" in task_lower or "instance" in task_lower:
            services.append("ec2")
        if "s3" in task_lower or "bucket" in task_lower or "storage" in task_lower:
            services.append("s3")
        if "rds" in task_lower or "database" in task_lower or "db" in task_lower:
            services.append("rds")
        if "lambda" in task_lower or "serverless" in task_lower or "function" in task_lower:
            services.append("lambda")
        if "elb" in task_lower or "load balancer" in task_lower or "balancer" in task_lower:
            services.append("elb")
        if "ecs" in task_lower or "container" in task_lower or "fargate" in task_lower:
            services.append("ecs")

        if not services or "all" in task_lower or "discover" in task_lower or "inventory" in task_lower:
            return "ec2,s3,rds,lambda,ecs,elb"
        return ",".join(services)
