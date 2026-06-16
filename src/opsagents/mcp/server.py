"""MCP Server for OpsAgents.

Exposes all 10 agents as MCP tools and implements human-in-the-loop interruption/resume
protocols for external coding agents (Cursor, Claude Code, etc.).
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import FastMCP

if TYPE_CHECKING:
    from opsagents.config import OpsAgentsConfig

logger = logging.getLogger(__name__)

# Global configuration reference to be populated on server startup
_global_config: OpsAgentsConfig | None = None

# Initialize FastMCP server
mcp = FastMCP("opsagents")


def _get_agent(agent_type: str) -> Any:
    """Helper to instantiate agents with the global config."""
    global _global_config
    if _global_config is None:
        raise ValueError("MCP Server configuration not initialized.")

    # Lazy import to avoid circular dependencies
    from opsagents.cloud import (
        ArchitectureAgent,
        CostAgent,
        IncidentAgent,
        InfrastructureAgent,
        SecurityAgent,
    )
    from opsagents.devops import (
        CICDAgent,
        ContainerSecurityAgent,
        GitOpsAgent,
        KubernetesAgent,
        MonitoringAgent,
    )

    agent_classes: dict[str, Any] = {
        "infra": InfrastructureAgent,
        "security": SecurityAgent,
        "cost": CostAgent,
        "incident": IncidentAgent,
        "architect": ArchitectureAgent,
        "cicd": CICDAgent,
        "k8s": KubernetesAgent,
        "monitor": MonitoringAgent,
        "gitops": GitOpsAgent,
        "container": ContainerSecurityAgent,
    }

    if agent_type not in agent_classes:
        raise ValueError(f"Unknown agent type: {agent_type}")

    return agent_classes[agent_type](config=_global_config, mode="mcp")


def _run_agent_tool(agent_type: str, task: str, thread_id: str | None = None) -> dict[str, Any]:
    """Execute agent tool logic and check for approval interrupts."""
    agent = _get_agent(agent_type)
    tid = thread_id or f"mcp-{agent_type}-{uuid.uuid4().hex[:8]}"

    try:
        state = agent.run(task, thread_id=tid)

        # Check if execution paused at approval gate (returns interrupt schema in state)
        approval_response = state.get("approval_response")
        if isinstance(approval_response, dict) and approval_response.get("type") == "approval_required":
            return {
                "status": "paused_for_approval",
                "thread_id": tid,
                "agent_type": agent_type,
                "message": approval_response.get("message"),
                "approval_request": approval_response.get("request"),
            }

        # Otherwise execution completed normally
        return {
            "status": "completed",
            "thread_id": tid,
            "agent_type": agent_type,
            "report": state.get("final_report", "No report generated"),
            "results": [
                {
                    "action": r.action,
                    "success": r.success,
                    "output": r.output if r.success else None,
                    "error": r.error if not r.success else None,
                }
                for r in state.get("results", [])
            ],
        }
    except Exception as e:
        logger.error("Error executing agent tool %s: %s", agent_type, e, exc_info=True)
        return {
            "status": "failed",
            "thread_id": tid,
            "agent_type": agent_type,
            "error": str(e),
        }


# ── Registered MCP Tools ─────────────────────────────────────────────


@mcp.tool()
def run_infra_agent(task: str, thread_id: str | None = None) -> dict[str, Any]:
    """Execute Infrastructure Provisioner Agent (Terraform/CloudFormation changes).

    Args:
        task: Natural language requirements for infrastructure.
        thread_id: Optional ID to preserve session history.
    """
    return _run_agent_tool("infra", task, thread_id)


@mcp.tool()
def run_security_agent(task: str, thread_id: str | None = None) -> dict[str, Any]:
    """Execute Security & Compliance Agent (Scan bucket settings, SGs, policies).

    Args:
        task: Security scan instructions.
        thread_id: Optional ID to preserve session history.
    """
    return _run_agent_tool("security", task, thread_id)


@mcp.tool()
def run_cost_agent(task: str, thread_id: str | None = None) -> dict[str, Any]:
    """Execute Cost Optimizer Agent (Identify unused resources, Rightsizing).

    Args:
        task: Cost audit instructions.
        thread_id: Optional ID to preserve session history.
    """
    return _run_agent_tool("cost", task, thread_id)


@mcp.tool()
def run_incident_agent(task: str, thread_id: str | None = None) -> dict[str, Any]:
    """Execute Incident Response Agent (Analyze logs/alarms, execute runbooks).

    Args:
        task: Active incident diagnosis task.
        thread_id: Optional ID to preserve session history.
    """
    return _run_agent_tool("incident", task, thread_id)


@mcp.tool()
def run_architect_agent(task: str, thread_id: str | None = None) -> dict[str, Any]:
    """Execute Architecture Review Agent (AWS Well-Architected assessment).

    Args:
        task: System review task.
        thread_id: Optional ID to preserve session history.
    """
    return _run_agent_tool("architect", task, thread_id)


@mcp.tool()
def run_cicd_agent(task: str, thread_id: str | None = None) -> dict[str, Any]:
    """Execute CI/CD Pipeline Agent (Generate/optimize actions, debug runs).

    Args:
        task: CI/CD configuration task.
        thread_id: Optional ID to preserve session history.
    """
    return _run_agent_tool("cicd", task, thread_id)


@mcp.tool()
def run_k8s_agent(task: str, thread_id: str | None = None) -> dict[str, Any]:
    """Execute Kubernetes Operations Agent (Troubleshoot pods, scale, manifests).

    Args:
        task: Kubernetes administrative task.
        thread_id: Optional ID to preserve session history.
    """
    return _run_agent_tool("k8s", task, thread_id)


@mcp.tool()
def run_monitor_agent(task: str, thread_id: str | None = None) -> dict[str, Any]:
    """Execute Monitoring & Observability Agent (Prometheus, Grafana, CloudWatch).

    Args:
        task: Monitoring setup task.
        thread_id: Optional ID to preserve session history.
    """
    return _run_agent_tool("monitor", task, thread_id)


@mcp.tool()
def run_gitops_agent(task: str, thread_id: str | None = None) -> dict[str, Any]:
    """Execute GitOps & Release Agent (ArgoCD apps, Canary rollouts, changelogs).

    Args:
        task: GitOps promotion or config task.
        thread_id: Optional ID to preserve session history.
    """
    return _run_agent_tool("gitops", task, thread_id)


@mcp.tool()
def run_container_agent(task: str, thread_id: str | None = None) -> dict[str, Any]:
    """Execute Container Security Agent (Trivy scans, Dockerfile audits).

    Args:
        task: Container vulnerability auditing task.
        thread_id: Optional ID to preserve session history.
    """
    return _run_agent_tool("container", task, thread_id)


@mcp.tool()
def resume_agent(thread_id: str, approval_response: str, agent_type: str) -> dict[str, Any]:
    """Resume a paused agent run by providing human approval feedback.

    Args:
        thread_id: The thread ID of the paused agent session.
        approval_response: The response (e.g., 'approve' or 'deny').
        agent_type: The type of agent (e.g. infra, security, k8s, cicd).
    """
    agent = _get_agent(agent_type)
    try:
        state = agent.resume(thread_id=thread_id, response=approval_response)

        # If paused again (multi-step approvals), return approval details
        next_approval = state.get("approval_response")
        if isinstance(next_approval, dict) and next_approval.get("type") == "approval_required":
            return {
                "status": "paused_for_approval",
                "thread_id": thread_id,
                "agent_type": agent_type,
                "message": next_approval.get("message"),
                "approval_request": next_approval.get("request"),
            }

        # Completed
        return {
            "status": "completed",
            "thread_id": thread_id,
            "agent_type": agent_type,
            "report": state.get("final_report", "No report generated"),
            "results": [
                {
                    "action": r.action,
                    "success": r.success,
                    "output": r.output if r.success else None,
                    "error": r.error if not r.success else None,
                }
                for r in state.get("results", [])
            ],
        }
    except Exception as e:
        logger.error("Error resuming agent %s on thread %s: %s", agent_type, thread_id, e)
        return {
            "status": "failed",
            "thread_id": thread_id,
            "agent_type": agent_type,
            "error": str(e),
        }


# ── Server Startup ───────────────────────────────────────────────────


def run_mcp_server(config: OpsAgentsConfig) -> None:
    """Start the MCP server stdio/SSE runner based on loaded settings."""
    global _global_config
    _global_config = config

    transport = config.mcp.transport.lower()
    if transport == "sse":
        host = config.mcp.sse_host
        port = config.mcp.sse_port
        mcp.settings.host = host
        mcp.settings.port = port
        logger.info("Starting MCP server over SSE on http://%s:%d", host, port)
        mcp.run(transport="sse")
    else:
        logger.info("Starting MCP server over stdio")
        mcp.run(transport="stdio")
