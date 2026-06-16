"""GitOps & Release Agent.

Configures ArgoCD Applications, determines deployment release rollout strategies,
generates changelogs, manages semantic versions, and monitors rollbacks.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from opsagents.core.base_agent import BaseAgent
from opsagents.core.state import ActionResult, AgentState
from opsagents.devops.gitops.prompts import (
    CHANGELOG_GENERATION_PROMPT,
    RELEASE_PLANNING_PROMPT,
    SYSTEM_PROMPT,
)
from opsagents.devops.gitops.tools import get_gitops_tools

logger = logging.getLogger(__name__)


class GitOpsAgent(BaseAgent):
    """GitOps & Release Agent.

    Capabilities:
    - Setup ArgoCD application definitions
    - Design Canary/Blue-Green/Rolling release strategies
    - Compile markdown changelogs from commit records
    - Execute semver-compliant version updates
    - Coordinate GitOps rollbacks
    - Perform post-deploy smoke testing validation
    """

    @property
    def name(self) -> str:
        return "GitOps & Release"

    @property
    def description(self) -> str:
        return (
            "Deploys applications through GitOps automation, manages versioning "
            "and changelogs, plans Canary rollouts, and oversees deployment verification."
        )

    @property
    def system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def get_tools(self) -> list[Any]:
        return get_gitops_tools()

    def analyze(self, state: AgentState) -> dict[str, Any]:
        """Analyze the GitOps or release request."""
        task = state["task"]
        analysis = self.invoke_llm(
            f"Analyze this GitOps/Release task and determine what steps to run:\n\n{task}\n\n"
            f"Determine:\n1. Core action (setup ArgoCD, release planning, versioning, changelog, rollback, validate)\n"
            f"2. Scope (application name, git repository, target environment)\n"
            f"3. Risk profile of the deployment/release operation"
        )
        return {
            "context": {
                "analysis": analysis,
                "task_type": self._classify_task(task),
            },
            "messages": [HumanMessage(content=task), AIMessage(content=analysis)],
        }

    def create_plan(self, state: AgentState) -> dict[str, Any]:
        """Create GitOps and release action plan."""
        context = state.get("context", {})
        task_type = context.get("task_type", "setup")
        task = state["task"]

        actions = []
        if task_type == "strategy":
            actions.append({
                "action": "Plan application release strategy",
                "resource": "Rollout plan configuration",
                "risk_level": "low",
                "type": "plan_strategy",
                "app_name": "web-app",
                "method": self._determine_strategy_method(task),
            })
        elif task_type == "changelog":
            actions.append({
                "action": "Compile release changelog",
                "resource": "Changelog text",
                "risk_level": "low",
                "type": "draft_changelog",
                "commits": "feat: add user authentication\nfix: resolved db timeout in api\nchore: updated requirements",
            })
        elif task_type == "version":
            actions.append({
                "action": "Determine version bump",
                "resource": "Semantic versioning",
                "risk_level": "medium",
                "type": "bump_version",
                "current": "1.2.3",
                "bump": "minor",
            })
        elif task_type == "rollback":
            actions.append({
                "action": "Perform deployment rollback",
                "resource": "GitOps environment config",
                "risk_level": "high",
                "type": "rollback_run",
                "app_name": "web-app",
                "env": "production",
            })
        elif task_type == "validate":
            actions.append({
                "action": "Verify post-deployment smoke test",
                "resource": "Endpoint validation",
                "risk_level": "low",
                "type": "validate_run",
                "url": "https://app.example.com/healthz",
            })
        else:
            # Default setup ArgoCD
            actions.append({
                "action": "Setup ArgoCD application configuration",
                "resource": "ArgoCD Application CRD",
                "risk_level": "medium",
                "type": "argocd_setup",
                "app_name": "web-app",
                "repo": "https://github.com/example/web-app-gitops.git",
                "path": "deploy/manifests",
            })

        return {"action_plan": actions}

    def execute_action(self, state: AgentState, action: dict[str, Any]) -> ActionResult:
        """Execute a GitOps release action."""
        action_type = action.get("type", "")

        from opsagents.devops.gitops.tools import (
            generate_changelog,
            manage_version,
            plan_release_strategy,
            rollback_release,
            setup_argocd_app,
            validate_deployment,
        )

        if action_type == "argocd_setup":
            app = action.get("app_name", "web-app")
            repo = action.get("repo", "")
            path = action.get("path", "")
            try:
                result = setup_argocd_app.invoke({
                    "app_name": app,
                    "repo_url": repo,
                    "path": path
                })
                return ActionResult(success=True, action=action["action"], output=str(result))
            except Exception as e:
                return ActionResult(success=False, action=action["action"], error=str(e))

        elif action_type == "plan_strategy":
            app = action.get("app_name", "web-app")
            method = action.get("method", "rolling")
            try:
                prompt = RELEASE_PLANNING_PROMPT.format(
                    app_name=app,
                    environment="production",
                    method=method
                )
                suggested_plan = self.invoke_llm(prompt)

                result = plan_release_strategy.invoke({
                    "app_name": app,
                    "method": method
                })
                output_str = f"LLM Recommendations:\n{suggested_plan}\n\nTool Output:\n{result}"
                return ActionResult(success=True, action=action["action"], output=output_str)
            except Exception as e:
                return ActionResult(success=False, action=action["action"], error=str(e))

        elif action_type == "draft_changelog":
            commits = action.get("commits", "")
            try:
                prompt = CHANGELOG_GENERATION_PROMPT.format(commits=commits)
                suggested_changelog = self.invoke_llm(prompt)

                result = generate_changelog.invoke({"commits": commits})
                output_str = f"LLM Recommendations:\n{suggested_changelog}\n\nTool Output:\n{result}"
                return ActionResult(success=True, action=action["action"], output=output_str)
            except Exception as e:
                return ActionResult(success=False, action=action["action"], error=str(e))

        elif action_type == "bump_version":
            current = action.get("current", "1.2.3")
            bump = action.get("bump", "minor")
            try:
                result = manage_version.invoke({
                    "current_version": current,
                    "bump_type": bump
                })
                return ActionResult(success=True, action=action["action"], output=str(result))
            except Exception as e:
                return ActionResult(success=False, action=action["action"], error=str(e))

        elif action_type == "rollback_run":
            app = action.get("app_name", "web-app")
            env = action.get("env", "production")
            try:
                result = rollback_release.invoke({
                    "app_name": app,
                    "environment": env
                })
                return ActionResult(success=True, action=action["action"], output=str(result))
            except Exception as e:
                return ActionResult(success=False, action=action["action"], error=str(e))

        elif action_type == "validate_run":
            url = action.get("url", "")
            try:
                result = validate_deployment.invoke({"target_url": url})
                return ActionResult(success=True, action=action["action"], output=str(result))
            except Exception as e:
                return ActionResult(success=False, action=action["action"], error=str(e))

        return ActionResult(success=False, action=action["action"], error="Unknown action type")

    def _classify_task(self, task: str) -> str:
        """Classify release/GitOps task."""
        task_lower = task.lower()
        if any(w in task_lower for w in ["strategy", "canary", "blue", "green", "rollout", "plan"]):
            return "strategy"
        elif any(w in task_lower for w in ["changelog", "commits", "history"]):
            return "changelog"
        elif any(w in task_lower for w in ["version", "tag", "bump"]):
            return "version"
        elif any(w in task_lower for w in ["rollback", "revert", "undo"]):
            return "rollback"
        elif any(w in task_lower for w in ["validate", "test", "smoke", "health"]):
            return "validate"
        return "setup"

    def _determine_strategy_method(self, task: str) -> str:
        """Determine canary vs bluegreen vs rolling update."""
        task_lower = task.lower()
        if "canary" in task_lower:
            return "canary"
        elif "blue" in task_lower or "green" in task_lower:
            return "blue-green"
        return "rolling"
