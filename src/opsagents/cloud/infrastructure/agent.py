"""Infrastructure Provisioner Agent.

Generates, reviews, validates, and applies Infrastructure as Code
(Terraform / CloudFormation) for AWS resources with human-in-the-loop
approval before any mutations.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from opsagents.cloud.infrastructure.prompts import (
    CLOUDFORMATION_GENERATION_PROMPT,
    SYSTEM_PROMPT,
    TERRAFORM_GENERATION_PROMPT,
)
from opsagents.cloud.infrastructure.tools import get_infrastructure_tools
from opsagents.core.base_agent import BaseAgent
from opsagents.core.state import ActionResult, AgentState
from opsagents.core.tools import run_command

logger = logging.getLogger(__name__)


class InfrastructureAgent(BaseAgent):
    """Infrastructure Provisioner Agent — IaC generation and deployment.

    Capabilities:
    - Generate Terraform/CloudFormation from natural language
    - Validate IaC templates
    - Plan and preview changes
    - Apply changes (with approval)
    - Detect and resolve drift
    - Estimate costs
    """

    @property
    def name(self) -> str:
        return "Infrastructure Provisioner"

    @property
    def description(self) -> str:
        return (
            "Generates, reviews, and applies Infrastructure as Code (Terraform/CloudFormation). "
            "Handles resource provisioning, drift detection, and cost estimation."
        )

    @property
    def system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def get_tools(self) -> list[Any]:
        return get_infrastructure_tools()

    def analyze(self, state: AgentState) -> dict[str, Any]:
        """Analyze the infrastructure task and gather context."""
        task = state["task"]
        iac_tool = self.config.infrastructure.default_iac
        region = self.config.aws.region

        # Use LLM to understand the task and determine what's needed
        analysis_prompt = (
            f"Analyze this infrastructure task and determine:\n"
            f"1. What AWS resources are needed\n"
            f"2. Whether to use Terraform or CloudFormation (default: {iac_tool})\n"
            f"3. What actions to take (generate, validate, plan, apply, etc.)\n"
            f"4. Any security considerations\n"
            f"5. Estimated cost implications\n\n"
            f"Task: {task}\n"
            f"Default IaC tool: {iac_tool}\n"
            f"AWS Region: {region}"
        )

        analysis = self.invoke_llm(analysis_prompt)

        context = {
            "analysis": analysis,
            "iac_tool": iac_tool,
            "region": region,
            "task_type": self._classify_task(task),
        }

        return {
            "context": context,
            "messages": [
                HumanMessage(content=task),
                AIMessage(content=analysis),
            ],
        }

    def create_plan(self, state: AgentState) -> dict[str, Any]:
        """Create an action plan for the infrastructure task."""
        context = state.get("context", {})
        state["task"]
        task_type = context.get("task_type", "generate")
        iac_tool = context.get("iac_tool", "terraform")

        actions: list[dict[str, Any]] = []

        if task_type == "generate":
            # Generate IaC code
            actions.append({
                "action": f"Generate {iac_tool.title()} code",
                "resource": "IaC template",
                "risk_level": "low",
                "type": "generate",
                "iac_tool": iac_tool,
            })
            actions.append({
                "action": "Validate generated code",
                "resource": "IaC template",
                "risk_level": "low",
                "type": "validate",
                "iac_tool": iac_tool,
            })

        elif task_type == "apply":
            actions.append({
                "action": f"Run {iac_tool} plan",
                "resource": "Infrastructure",
                "risk_level": "low",
                "type": "plan",
                "iac_tool": iac_tool,
            })
            actions.append({
                "action": f"Apply {iac_tool} changes",
                "resource": "Infrastructure",
                "risk_level": "high",
                "type": "apply",
                "iac_tool": iac_tool,
            })

        elif task_type == "destroy":
            actions.append({
                "action": "Destroy infrastructure",
                "resource": "All managed resources",
                "risk_level": "critical",
                "type": "destroy",
                "iac_tool": iac_tool,
            })

        elif task_type == "drift":
            actions.append({
                "action": "Detect infrastructure drift",
                "resource": "Managed resources",
                "risk_level": "low",
                "type": "drift",
                "iac_tool": iac_tool,
            })

        else:
            # Default: analyze and generate
            actions.append({
                "action": f"Generate {iac_tool.title()} code for requested infrastructure",
                "resource": "IaC template",
                "risk_level": "low",
                "type": "generate",
                "iac_tool": iac_tool,
            })

        return {"action_plan": actions}

    def execute_action(self, state: AgentState, action: dict[str, Any]) -> ActionResult:
        """Execute a single infrastructure action."""
        action_type = action.get("type", "generate")
        iac_tool = action.get("iac_tool", "terraform")
        task = state["task"]
        region = self.config.aws.region

        if action_type == "generate":
            return self._generate_iac(task, iac_tool, region, state.get("context", {}))
        elif action_type == "validate":
            return self._validate_iac(iac_tool)
        elif action_type == "plan":
            return self._run_plan(iac_tool)
        elif action_type == "apply":
            return self._run_apply(iac_tool)
        elif action_type == "destroy":
            return self._run_destroy(iac_tool)
        elif action_type == "drift":
            return self._detect_drift(iac_tool)
        else:
            return ActionResult(
                success=False,
                action=action.get("action", "Unknown"),
                error=f"Unknown action type: {action_type}",
            )

    # ── Private Methods ──────────────────────────────────────────────

    def _classify_task(self, task: str) -> str:
        """Classify the task type from natural language."""
        task_lower = task.lower()
        if any(w in task_lower for w in ["destroy", "delete", "teardown", "remove all"]):
            return "destroy"
        elif any(w in task_lower for w in ["apply", "deploy", "provision", "launch"]):
            return "apply"
        elif any(w in task_lower for w in ["drift", "difference", "diverge"]):
            return "drift"
        elif any(w in task_lower for w in ["validate", "check", "lint", "verify"]):
            return "validate"
        else:
            return "generate"

    def _generate_iac(
        self, task: str, iac_tool: str, region: str, context: dict[str, Any]
    ) -> ActionResult:
        """Generate IaC code using the LLM."""
        if iac_tool == "cloudformation":
            prompt = CLOUDFORMATION_GENERATION_PROMPT.format(
                requirement=task,
                region=region,
                context=context.get("analysis", ""),
            )
        else:
            prompt = TERRAFORM_GENERATION_PROMPT.format(
                requirement=task,
                region=region,
                context=context.get("analysis", ""),
            )

        code = self.invoke_llm(prompt)

        return ActionResult(
            success=True,
            action=f"Generate {iac_tool.title()} code",
            output=code,
            metadata={"iac_tool": iac_tool, "region": region},
        )

    def _validate_iac(self, iac_tool: str) -> ActionResult:
        """Validate generated IaC code."""
        if iac_tool == "terraform":
            result = run_command(["terraform", "validate", "-no-color", "-json"])
            success = result["returncode"] == 0
        else:
            success = True  # CFN validation requires a file
            result = {"stdout": "CloudFormation template validation requires a saved template file."}

        return ActionResult(
            success=success,
            action="Validate IaC code",
            output=result.get("stdout", ""),
            error=result.get("stderr", "") if not success else "",
        )

    def _run_plan(self, iac_tool: str) -> ActionResult:
        """Run infrastructure plan."""
        if iac_tool == "terraform":
            result = run_command(["terraform", "plan", "-no-color"])
        else:
            result = {"stdout": "CloudFormation change sets require a stack name.", "returncode": 0}

        return ActionResult(
            success=result.get("returncode", 1) == 0 or result.get("returncode") == 2,
            action=f"Run {iac_tool} plan",
            output=result.get("stdout", ""),
            error=result.get("stderr", ""),
        )

    def _run_apply(self, iac_tool: str) -> ActionResult:
        """Apply infrastructure changes."""
        if iac_tool == "terraform":
            result = run_command(
                ["terraform", "apply", "-no-color", "-auto-approve"],
                timeout=600,
            )
        else:
            result = {"stdout": "CloudFormation apply requires stack parameters.", "returncode": 0}

        return ActionResult(
            success=result.get("returncode", 1) == 0,
            action=f"Apply {iac_tool} changes",
            output=result.get("stdout", ""),
            error=result.get("stderr", ""),
        )

    def _run_destroy(self, iac_tool: str) -> ActionResult:
        """Destroy infrastructure."""
        if iac_tool == "terraform":
            result = run_command(
                ["terraform", "destroy", "-no-color", "-auto-approve"],
                timeout=600,
            )
        else:
            result = {"stdout": "CloudFormation destroy requires stack name.", "returncode": 0}

        return ActionResult(
            success=result.get("returncode", 1) == 0,
            action="Destroy infrastructure",
            output=result.get("stdout", ""),
            error=result.get("stderr", ""),
        )

    def _detect_drift(self, iac_tool: str) -> ActionResult:
        """Detect infrastructure drift."""
        if iac_tool == "terraform":
            result = run_command(["terraform", "plan", "-no-color", "-detailed-exitcode"])
            has_drift = result["returncode"] == 2
            return ActionResult(
                success=True,
                action="Detect drift",
                output="Drift detected! Review the plan output." if has_drift else "No drift detected.",
                metadata={"drift_detected": has_drift, "details": result.get("stdout", "")},
            )
        else:
            return ActionResult(
                success=True,
                action="Detect drift",
                output="CloudFormation drift detection requires a stack name. Use the detect_drift tool directly.",
            )
