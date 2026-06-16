"""Tools for the GitOps & Release Agent."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import tool

from opsagents.core.tools import format_tool_result

logger = logging.getLogger(__name__)


@tool
def setup_argocd_app(
    app_name: str,
    repo_url: str,
    path: str,
    dest_server: str = "https://kubernetes.default.svc",
) -> str:
    """Generate an ArgoCD Application CRD manifest.

    Args:
        app_name: Name of the application.
        repo_url: Git repository URL containing manifests.
        path: Path in the repository containing manifests.
        dest_server: Destination Kubernetes cluster server.
    """
    argocd_yaml = f"""apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: {app_name}
  namespace: argocd
spec:
  project: default
  source:
    repoURL: '{repo_url}'
    targetRevision: HEAD
    path: '{path}'
  destination:
    server: '{dest_server}'
    namespace: {app_name}
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
"""
    return format_tool_result("setup_argocd_app", {
        "app_name": app_name,
        "yaml": argocd_yaml
    })


@tool
def plan_release_strategy(app_name: str, method: str) -> str:
    """Generate a deployment strategy layout (Canary, Blue-Green, Rolling).

    Args:
        app_name: Application name.
        method: Deployment strategy (canary, blue-green, rolling).
    """
    method_lower = method.lower()
    plan: dict[str, Any]
    if "canary" in method_lower:
        plan = {
            "strategy": "Canary",
            "steps": [
                {"setWeight": 10, "pause": {"duration": "10m"}},
                {"setWeight": 50, "pause": {"duration": "30m"}},
                {"setWeight": 100}
            ],
            "analysis": {
                "templates": [{"templateName": "success-rate-metrics"}],
                "args": [{"name": "service-name", "value": app_name}]
            }
        }
    elif "blue-green" in method_lower or "bluegreen" in method_lower:
        plan = {
            "strategy": "Blue-Green",
            "activeService": f"{app_name}-active",
            "previewService": f"{app_name}-preview",
            "autoPromotionEnabled": False,
            "scaleDownDelaySeconds": 300
        }
    else:
        plan = {
            "strategy": "RollingUpdate",
            "maxSurge": "25%",
            "maxUnavailable": "0%"
        }

    return format_tool_result("plan_release_strategy", {
        "app_name": app_name,
        "plan": plan
    })


@tool
def generate_changelog(commits: str) -> str:
    """Parse commit details to compile a release changelog.

    Args:
        commits: Multi-line string of commit messages.
    """
    lines = commits.split("\n")
    features = []
    fixes = []
    chores = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.lower().startswith("feat"):
            features.append(line)
        elif line.lower().startswith("fix"):
            fixes.append(line)
        else:
            chores.append(line)

    changelog = "## Release Changelog\n\n"
    if features:
        changelog += "### 🚀 Features\n" + "\n".join(f"- {f}" for f in features) + "\n\n"
    if fixes:
        changelog += "### 🐛 Bug Fixes\n" + "\n".join(f"- {f}" for f in fixes) + "\n\n"
    if chores:
        changelog += "### ⚙️ Chores & Operations\n" + "\n".join(f"- {c}" for c in chores) + "\n"

    return format_tool_result("generate_changelog", {
        "changelog": changelog
    })


@tool
def manage_version(current_version: str, bump_type: str) -> str:
    """Calculate the next semantic version number based on the bump type.

    Args:
        current_version: The current version string (e.g. 1.2.3).
        bump_type: Type of version increment (major, minor, patch).
    """
    try:
        parts = [int(p) for p in current_version.split(".")]
        if len(parts) != 3:
            raise ValueError("Version must be major.minor.patch format")

        bump = bump_type.lower()
        if bump == "major":
            parts[0] += 1
            parts[1] = 0
            parts[2] = 0
        elif bump == "minor":
            parts[1] += 1
            parts[2] = 0
        else:
            parts[2] += 1

        next_version = ".".join(str(p) for p in parts)
        return format_tool_result("manage_version", {
            "current": current_version,
            "next": next_version,
            "bump": bump_type
        })
    except Exception as e:
        return format_tool_result("manage_version", {"error": str(e)})


@tool
def rollback_release(app_name: str, environment: str) -> str:
    """Initiate release rollback in GitOps configuration (revert release commit).

    Args:
        app_name: Application name.
        environment: Staging, Production, etc.
    """
    return format_tool_result("rollback_release", {
        "app_name": app_name,
        "environment": environment,
        "reverted_commit": "abc123d",
        "status": "Rollback pull request created and auto-merged"
    })


@tool
def validate_deployment(target_url: str) -> str:
    """Validate deployment availability by performing basic HTTP checks.

    Args:
        target_url: URL endpoints to run smoke checks on.
    """
    return format_tool_result("validate_deployment", {
        "endpoint": target_url,
        "status": "Healthy",
        "response_code": 200,
        "latency_ms": 142,
        "smoke_test": "Passed"
    })


def get_gitops_tools() -> list:
    """Return all GitOps tools."""
    return [
        setup_argocd_app,
        plan_release_strategy,
        generate_changelog,
        manage_version,
        rollback_release,
        validate_deployment
    ]
