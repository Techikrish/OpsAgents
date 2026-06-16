"""OpsAgents — Production-ready Cloud & DevOps AI Agents.

A suite of 10 intelligent AI agents built with LangGraph that assist
cloud and DevOps engineers in their daily work. Supports multiple LLM
providers and integrates with coding agents via MCP.
"""

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

__version__ = "0.1.0"
__all__ = [
    "ArchitectureAgent",
    "CICDAgent",
    "ContainerSecurityAgent",
    "CostAgent",
    "GitOpsAgent",
    "IncidentAgent",
    "InfrastructureAgent",
    "KubernetesAgent",
    "MonitoringAgent",
    "SecurityAgent",
    "__version__",
]

