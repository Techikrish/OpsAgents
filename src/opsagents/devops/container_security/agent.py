"""Container & Image Security Agent.

Scans container images for vulnerabilities, optimizes Dockerfiles, validates base image
updates, audits Software Bill of Materials (SBOMs), and verifies supply-chain safety.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from opsagents.core.base_agent import BaseAgent
from opsagents.core.state import ActionResult, AgentState
from opsagents.devops.container_security.prompts import (
    DOCKERFILE_OPTIMIZATION_PROMPT,
    SYSTEM_PROMPT,
    VULNERABILITY_REMEDIATION_PROMPT,
)
from opsagents.devops.container_security.tools import get_container_security_tools

logger = logging.getLogger(__name__)


class ContainerSecurityAgent(BaseAgent):
    """Container & Image Security Agent.

    Capabilities:
    - Scan container images for CVE vulnerability indices
    - Audit and rewrite Dockerfiles to meet security benchmarks
    - Audit base images for upstream security updates
    - Scaffold and verify SBOM details
    - Verify image signing and verify signature trust policies
    - Scan package manager lockfiles (Pip, NPM, Cargo)
    """

    @property
    def name(self) -> str:
        return "Container & Image Security"

    @property
    def description(self) -> str:
        return (
            "Scans docker images for CVE vulnerabilities, optimizes Dockerfiles "
            "for size and safety, and audits package dependency lockfiles."
        )

    @property
    def system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def get_tools(self) -> list[Any]:
        return get_container_security_tools()

    def analyze(self, state: AgentState) -> dict[str, Any]:
        """Analyze the container/image security request."""
        task = state["task"]
        analysis = self.invoke_llm(
            f"Analyze this container security task and determine what steps to run:\n\n{task}\n\n"
            f"Determine:\n1. Task category (image scan, Dockerfile optimize, base update, SBOM, signing check, dependency check)\n"
            f"2. Scope (image name, file path, lockfile type)\n"
            f"3. Potential high-risk items (vulnerabilities found, root execution)"
        )
        return {
            "context": {
                "analysis": analysis,
                "task_type": self._classify_task(task),
            },
            "messages": [HumanMessage(content=task), AIMessage(content=analysis)],
        }

    def create_plan(self, state: AgentState) -> dict[str, Any]:
        """Create container security action plan."""
        context = state.get("context", {})
        task_type = context.get("task_type", "scan")
        state["task"]

        actions = []
        if task_type == "optimize":
            actions.append({
                "action": "Audit and optimize Dockerfile",
                "resource": "Dockerfile config",
                "risk_level": "low",
                "type": "dockerfile_optimize",
                "path": "Dockerfile",
            })
        elif task_type == "base":
            actions.append({
                "action": "Check base image security updates",
                "resource": "Base image tag",
                "risk_level": "low",
                "type": "base_update_check",
                "image": "python:3.11-slim",
            })
        elif task_type == "sbom":
            actions.append({
                "action": "Generate Software Bill of Materials",
                "resource": "SBOM json",
                "risk_level": "low",
                "type": "sbom_generate",
                "image": "my-app:latest",
            })
        elif task_type == "signing":
            actions.append({
                "action": "Verify container image signing signature",
                "resource": "Cosign signing record",
                "risk_level": "low",
                "type": "signing_check",
                "image": "my-app:latest",
            })
        elif task_type == "lockfile":
            actions.append({
                "action": "Audit lockfile package dependencies",
                "resource": "Project package lockfile",
                "risk_level": "low",
                "type": "lockfile_check",
                "path": "poetry.lock",
            })
        else:
            # Default is image vulnerability scan
            actions.append({
                "action": "Run image vulnerability scan",
                "resource": "Container image layers",
                "risk_level": "low",
                "type": "image_scan",
                "image": "my-app:latest",
            })

        return {"action_plan": actions}

    def execute_action(self, state: AgentState, action: dict[str, Any]) -> ActionResult:
        """Execute a container security agent action."""
        action_type = action.get("type", "")

        from opsagents.devops.container_security.tools import (
            check_base_image_updates,
            enforce_signing_policy,
            generate_image_sbom,
            optimize_dockerfile,
            scan_image_trivy,
            scan_supply_chain,
        )

        if action_type == "image_scan":
            image = action.get("image", "my-app:latest")
            try:
                result = scan_image_trivy.invoke({"image_name": image})

                # Request LLM for remediation plan
                try:
                    res_dict = json.loads(result)
                    res_data = res_dict.get("result", {})
                    remedy_prompt = VULNERABILITY_REMEDIATION_PROMPT.format(
                        image_name=image,
                        vulnerabilities=json.dumps(res_data.get("vulnerabilities", []))
                    )
                    remedy_plan = self.invoke_llm(remedy_prompt)
                    output_data = f"{result}\n\nLLM Mitigation Recommendations:\n{remedy_plan}"
                except Exception:
                    output_data = str(result)

                return ActionResult(success=True, action=action["action"], output=output_data)
            except Exception as e:
                return ActionResult(success=False, action=action["action"], error=str(e))

        elif action_type == "dockerfile_optimize":
            path = action.get("path", "Dockerfile")
            try:
                # Ask LLM to optimize
                try:
                    with open(path) as f:
                        dockerfile_content = f.read()
                except Exception:
                    dockerfile_content = "FROM python:3.11\nRUN pip install Flask\nCOPY . /app\nCMD python /app/main.py"

                prompt = DOCKERFILE_OPTIMIZATION_PROMPT.format(dockerfile_content=dockerfile_content)
                suggested_opts = self.invoke_llm(prompt)

                result = optimize_dockerfile.invoke({"dockerfile_path": path})
                output_str = f"LLM Recommendations:\n{suggested_opts}\n\nTool Output:\n{result}"
                return ActionResult(success=True, action=action["action"], output=output_str)
            except Exception as e:
                return ActionResult(success=False, action=action["action"], error=str(e))

        elif action_type == "base_update_check":
            image = action.get("image", "python:3.11-slim")
            try:
                result = check_base_image_updates.invoke({"image_name": image})
                return ActionResult(success=True, action=action["action"], output=str(result))
            except Exception as e:
                return ActionResult(success=False, action=action["action"], error=str(e))

        elif action_type == "sbom_generate":
            image = action.get("image", "my-app:latest")
            try:
                result = generate_image_sbom.invoke({"image_name": image})
                return ActionResult(success=True, action=action["action"], output=str(result))
            except Exception as e:
                return ActionResult(success=False, action=action["action"], error=str(e))

        elif action_type == "signing_check":
            image = action.get("image", "my-app:latest")
            try:
                result = enforce_signing_policy.invoke({"image_name": image})
                return ActionResult(success=True, action=action["action"], output=str(result))
            except Exception as e:
                return ActionResult(success=False, action=action["action"], error=str(e))

        elif action_type == "lockfile_check":
            path = action.get("path", "poetry.lock")
            try:
                result = scan_supply_chain.invoke({"lock_file_path": path})
                return ActionResult(success=True, action=action["action"], output=str(result))
            except Exception as e:
                return ActionResult(success=False, action=action["action"], error=str(e))

        return ActionResult(success=False, action=action["action"], error="Unknown action type")

    def _classify_task(self, task: str) -> str:
        """Classify container/image safety task."""
        task_lower = task.lower()
        if any(w in task_lower for w in ["dockerfile", "optimize", "rewrite", "multi-stage"]):
            return "optimize"
        elif any(w in task_lower for w in ["base", "upstream", "tag", "update"]):
            return "base"
        elif any(w in task_lower for w in ["sbom", "bill of materials", "cve list"]):
            return "sbom"
        elif any(w in task_lower for w in ["sign", "cosign", "signature", "verify image"]):
            return "signing"
        elif any(w in task_lower for w in ["lock", "lockfile", "poetry.lock", "package-lock", "dependency", "supply"]):
            return "lockfile"
        return "scan"
