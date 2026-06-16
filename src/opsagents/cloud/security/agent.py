"""Security & Compliance Agent.

Scans AWS resources for security vulnerabilities and compliance gaps,
generates reports, and remediates findings with human approval.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from opsagents.cloud.security.prompts import SCAN_ANALYSIS_PROMPT, SYSTEM_PROMPT
from opsagents.cloud.security.tools import get_security_tools
from opsagents.core.base_agent import BaseAgent
from opsagents.core.state import ActionResult, AgentState

logger = logging.getLogger(__name__)


class SecurityAgent(BaseAgent):
    """Security & Compliance Agent.

    Capabilities:
    - Scan IAM policies, security groups, S3 buckets
    - Analyze CloudTrail for suspicious activity
    - Validate against CIS AWS Foundations Benchmark
    - Generate compliance reports
    - Remediate findings (with approval)
    """

    @property
    def name(self) -> str:
        return "Security & Compliance"

    @property
    def description(self) -> str:
        return (
            "Scans IAM policies, security groups, S3 buckets, and CloudTrail. "
            "Detects misconfigurations and generates compliance reports."
        )

    @property
    def system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def get_tools(self) -> list[Any]:
        return get_security_tools()

    def analyze(self, state: AgentState) -> dict[str, Any]:
        """Analyze the security task."""
        task = state["task"]
        analysis = self.invoke_llm(
            f"Analyze this security task and determine what scans to run:\n\n{task}\n\n"
            f"Determine:\n1. What security areas to scan (IAM, SGs, S3, CloudTrail, CIS)\n"
            f"2. Scope of the scan\n3. Expected risk areas"
        )
        return {
            "context": {
                "analysis": analysis,
                "scan_types": self._determine_scan_types(task),
            },
            "messages": [HumanMessage(content=task), AIMessage(content=analysis)],
        }

    def create_plan(self, state: AgentState) -> dict[str, Any]:
        """Create a scanning and remediation plan."""
        scan_types = state.get("context", {}).get("scan_types", ["iam", "sg", "s3"])
        actions = []

        scan_map = {
            "iam": ("Scan IAM policies", "IAM policies"),
            "sg": ("Scan security groups", "EC2 security groups"),
            "s3": ("Scan S3 buckets", "S3 buckets"),
            "cloudtrail": ("Analyze CloudTrail", "CloudTrail logs"),
            "cis": ("Check CIS benchmark", "CIS controls"),
        }

        for scan_type in scan_types:
            if scan_type in scan_map:
                action_name, resource = scan_map[scan_type]
                actions.append({
                    "action": action_name,
                    "resource": resource,
                    "risk_level": "low",
                    "type": f"scan_{scan_type}",
                })

        actions.append({
            "action": "Generate compliance report",
            "resource": "All findings",
            "risk_level": "low",
            "type": "report",
        })

        return {"action_plan": actions}

    def execute_action(self, state: AgentState, action: dict[str, Any]) -> ActionResult:
        """Execute a security scan or remediation action."""
        action_type = action.get("type", "")
        region = self.config.aws.region
        profile = self.config.aws.profile

        from opsagents.cloud.security.tools import (
            check_cis_benchmark,
            scan_cloudtrail,
            scan_iam_policies,
            scan_s3_buckets,
            scan_security_groups,
        )

        tool_map = {
            "scan_iam": lambda: scan_iam_policies.invoke({"profile": profile, "region": region}),
            "scan_sg": lambda: scan_security_groups.invoke({"profile": profile, "region": region}),
            "scan_s3": lambda: scan_s3_buckets.invoke({"profile": profile, "region": region}),
            "scan_cloudtrail": lambda: scan_cloudtrail.invoke({"profile": profile, "region": region}),
            "scan_cis": lambda: check_cis_benchmark.invoke({"profile": profile, "region": region}),
        }

        if action_type in tool_map:
            try:
                result = tool_map[action_type]()
                return ActionResult(success=True, action=action["action"], output=str(result))
            except Exception as e:
                return ActionResult(success=False, action=action["action"], error=str(e))

        elif action_type == "report":
            results = state.get("results", [])
            all_findings = "\n\n".join(r.output for r in results if r.success)
            report = self.invoke_llm(
                SCAN_ANALYSIS_PROMPT.format(scan_results=all_findings)
            )
            return ActionResult(success=True, action="Generate report", output=report)

        return ActionResult(success=False, action=action["action"], error="Unknown action type")

    def _determine_scan_types(self, task: str) -> list[str]:
        """Determine which scans to run from the task description."""
        task_lower = task.lower()
        scans = []
        if any(w in task_lower for w in ["iam", "policy", "permission", "role", "user"]):
            scans.append("iam")
        if any(w in task_lower for w in ["security group", "sg", "port", "firewall", "ingress"]):
            scans.append("sg")
        if any(w in task_lower for w in ["s3", "bucket", "storage", "object"]):
            scans.append("s3")
        if any(w in task_lower for w in ["cloudtrail", "audit", "log", "suspicious", "activity"]):
            scans.append("cloudtrail")
        if any(w in task_lower for w in ["cis", "benchmark", "compliance", "framework"]):
            scans.append("cis")
        if not scans or "all" in task_lower or "full" in task_lower or "scan" in task_lower:
            scans = ["iam", "sg", "s3", "cis"]
        return scans
