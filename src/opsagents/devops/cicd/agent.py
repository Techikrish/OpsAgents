"""CI/CD Pipeline Agent.

Analyzes projects, creates pipeline configurations, validates workflow syntax,
and diagnoses failure runs.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from opsagents.core.base_agent import BaseAgent
from opsagents.core.state import ActionResult, AgentState
from opsagents.devops.cicd.prompts import (
    CICD_GENERATION_PROMPT,
    DEBUG_PIPELINE_PROMPT,
    SYSTEM_PROMPT,
)
from opsagents.devops.cicd.tools import get_cicd_tools

logger = logging.getLogger(__name__)


class CICDAgent(BaseAgent):
    """CI/CD Pipeline Agent.

    Capabilities:
    - Analyze repository language and dependencies
    - Generate CI/CD pipeline YAML (GitHub Actions, GitLab CI)
    - Validate pipeline syntax
    - Debug failed pipeline runs using execution logs
    """

    @property
    def name(self) -> str:
        return "CI/CD Pipeline"

    @property
    def description(self) -> str:
        return (
            "Scans codebase repositories, generates optimized CI/CD workflows, "
            "validates YAML configurations, and diagnoses build failures."
        )

    @property
    def system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def get_tools(self) -> list[Any]:
        return get_cicd_tools()

    def analyze(self, state: AgentState) -> dict[str, Any]:
        """Analyze the CI/CD request."""
        task = state["task"]
        analysis = self.invoke_llm(
            f"Analyze this CI/CD task and determine what steps to run:\n\n{task}\n\n"
            f"Determine:\n1. Type of operation (analyze repository, generate pipeline, debug failure, optimize)\n"
            f"2. Language/Build tool involved\n3. Key files affected (e.g. .github/workflows/ci.yml)"
        )
        return {
            "context": {
                "analysis": analysis,
                "task_type": self._classify_task(task),
            },
            "messages": [HumanMessage(content=task), AIMessage(content=analysis)],
        }

    def create_plan(self, state: AgentState) -> dict[str, Any]:
        """Create a CI/CD workflow action plan."""
        context = state.get("context", {})
        task_type = context.get("task_type", "generate")

        actions = []
        if task_type == "debug":
            actions.append({
                "action": "Fetch pipeline failure logs",
                "resource": "GitHub Actions run",
                "risk_level": "low",
                "type": "debug_fetch",
                "run_id": "1098234"
            })
            actions.append({
                "action": "Diagnose failure root cause",
                "resource": "Build logs analysis",
                "risk_level": "low",
                "type": "diagnose_report"
            })
        elif task_type == "optimize":
            actions.append({
                "action": "Analyze workflow configuration",
                "resource": ".github/workflows/ci.yml",
                "risk_level": "low",
                "type": "optimize_scan"
            })
        else:
            # Default is analyze repository and generate workflow
            actions.append({
                "action": "Analyze repository contents",
                "resource": "Repository files",
                "risk_level": "low",
                "type": "analyze_repo"
            })
            actions.append({
                "action": "Generate CI/CD pipeline template",
                "resource": ".github/workflows/ci.yml",
                "risk_level": "medium",
                "type": "generate_yaml"
            })
            actions.append({
                "action": "Validate generated workflow file",
                "resource": ".github/workflows/ci.yml",
                "risk_level": "low",
                "type": "validate_yaml"
            })

        return {"action_plan": actions}

    def execute_action(self, state: AgentState, action: dict[str, Any]) -> ActionResult:
        """Execute a CI/CD agent action."""
        action_type = action.get("type", "")

        from opsagents.devops.cicd.tools import (
            analyze_repository,
            debug_pipeline_failure,
            generate_github_actions,
            optimize_pipeline,
            validate_workflow,
        )

        if action_type == "analyze_repo":
            try:
                result = analyze_repository.invoke({})
                return ActionResult(success=True, action=action["action"], output=str(result))
            except Exception as e:
                return ActionResult(success=False, action=action["action"], error=str(e))

        elif action_type == "generate_yaml":
            results = state.get("results", [])
            lang = "python"
            build_system = "uv"
            for r in results:
                if r.success and "Analyze repository" in r.action:
                    try:
                        data = json.loads(r.output)
                        repo_res = data.get("result", {})
                        langs = repo_res.get("languages", [])
                        if langs:
                            lang = langs[0]
                        build_system = repo_res.get("build_system", "pip")
                    except Exception:
                        pass
                    break

            try:
                # LLM can guide the generation
                prompt = CICD_GENERATION_PROMPT.format(
                    project_info=f"Language: {lang}, Build system: {build_system}",
                    requirements=state["task"]
                )
                suggested_content = self.invoke_llm(prompt)

                result = generate_github_actions.invoke({
                    "lang": lang,
                    "build_system": build_system,
                    "output_path": ".github/workflows/ci.yml"
                })
                # Add LLM custom details to result output
                output_str = f"LLM Recommendations:\n{suggested_content}\n\nTool Output:\n{result}"
                return ActionResult(success=True, action=action["action"], output=output_str)
            except Exception as e:
                return ActionResult(success=False, action=action["action"], error=str(e))

        elif action_type == "validate_yaml":
            try:
                result = validate_workflow.invoke({"workflow_path": ".github/workflows/ci.yml"})
                return ActionResult(success=True, action=action["action"], output=str(result))
            except Exception as e:
                return ActionResult(success=False, action=action["action"], error=str(e))

        elif action_type == "optimize_scan":
            try:
                result = optimize_pipeline.invoke({"workflow_path": ".github/workflows/ci.yml"})
                return ActionResult(success=True, action=action["action"], output=str(result))
            except Exception as e:
                return ActionResult(success=False, action=action["action"], error=str(e))

        elif action_type == "debug_fetch":
            run_id = action.get("run_id", "1098234")
            try:
                result = debug_pipeline_failure.invoke({"run_id": run_id})
                return ActionResult(success=True, action=action["action"], output=str(result))
            except Exception as e:
                return ActionResult(success=False, action=action["action"], error=str(e))

        elif action_type == "diagnose_report":
            results = state.get("results", [])
            log_data = ""
            for r in results:
                if r.success and "Fetch pipeline" in r.action:
                    log_data = r.output
                    break

            report = self.invoke_llm(
                DEBUG_PIPELINE_PROMPT.format(
                    run_details="Workflow run failed.",
                    log_excerpt=log_data
                )
            )
            return ActionResult(success=True, action=action["action"], output=report)

        return ActionResult(success=False, action=action["action"], error="Unknown action type")

    def _classify_task(self, task: str) -> str:
        """Classify the task category."""
        task_lower = task.lower()
        if any(w in task_lower for w in ["debug", "fail", "error", "logs", "fix"]):
            return "debug"
        elif any(w in task_lower for w in ["optimize", "slow", "speed", "cache", "fast"]):
            return "optimize"
        return "generate"
