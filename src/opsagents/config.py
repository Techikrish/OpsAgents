"""Configuration loader — YAML files + environment variables.

Loads configuration from (in priority order):
1. CLI flags (highest)
2. Environment variables (OPSAGENTS_*)
3. config.yml in current directory
4. ~/.opsagents/config.yml
5. Built-in defaults (lowest)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

# ── Sub-models ───────────────────────────────────────────────────────


class LLMConfig(BaseModel):
    """LLM provider configuration."""

    provider: str = Field(default="openai", description="LLM provider name")
    model: str = Field(default="gpt-4o", description="Model identifier")
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, gt=0)
    fallback_provider: str | None = Field(default=None)
    fallback_model: str | None = Field(default=None)
    ollama_base_url: str = Field(default="http://localhost:11434")
    azure_deployment: str | None = Field(default=None)
    azure_api_version: str = Field(default="2024-10-21")


class RiskLevelPolicies(BaseModel):
    """Per-risk-level approval policies."""

    low: str = Field(default="auto", description="Policy for low-risk actions")
    medium: str = Field(default="prompt", description="Policy for medium-risk actions")
    high: str = Field(default="prompt", description="Policy for high-risk actions")
    critical: str = Field(default="confirm", description="Policy for critical actions")


class ApprovalConfig(BaseModel):
    """Human-in-the-loop approval settings."""

    default_policy: str = Field(default="prompt", description="auto | prompt | strict")
    risk_levels: RiskLevelPolicies = Field(default_factory=RiskLevelPolicies)
    timeout: int = Field(default=300, ge=0, description="Approval timeout in seconds")


class AWSConfig(BaseModel):
    """AWS provider settings."""

    profile: str = Field(default="default")
    region: str = Field(default="us-east-1")
    allowed_regions: list[str] = Field(default_factory=lambda: ["us-east-1"])


class KubernetesConfig(BaseModel):
    """Kubernetes cluster settings."""

    kubeconfig: str = Field(default="~/.kube/config")
    context: str = Field(default="")
    namespace: str = Field(default="default")


class GitHubConfig(BaseModel):
    """GitHub integration settings."""

    owner: str = Field(default="")
    repo: str = Field(default="")
    default_branch: str = Field(default="main")


class InfrastructureConfig(BaseModel):
    """Infrastructure provisioner settings."""

    default_iac: str = Field(default="terraform", description="terraform | cloudformation")
    terraform_dir: str = Field(default="./infrastructure")
    state_backend: str = Field(default="local", description="local | s3")


class MonitoringConfig(BaseModel):
    """Monitoring stack settings."""

    prometheus_url: str = Field(default="http://localhost:9090")
    grafana_url: str = Field(default="http://localhost:3000")
    datadog_site: str = Field(default="datadoghq.com")


class LoggingConfig(BaseModel):
    """Logging and audit settings."""

    level: str = Field(default="INFO")
    file: str = Field(default="")
    audit_trail: bool = Field(default=True)


class MCPConfig(BaseModel):
    """MCP server settings."""

    transport: str = Field(default="stdio", description="stdio | sse")
    sse_host: str = Field(default="0.0.0.0")
    sse_port: int = Field(default=8080)


# ── Root Config ──────────────────────────────────────────────────────


class OpsAgentsConfig(BaseModel):
    """Root configuration for OpsAgents."""

    llm: LLMConfig = Field(default_factory=LLMConfig)
    approval: ApprovalConfig = Field(default_factory=ApprovalConfig)
    aws: AWSConfig = Field(default_factory=AWSConfig)
    kubernetes: KubernetesConfig = Field(default_factory=KubernetesConfig)
    github: GitHubConfig = Field(default_factory=GitHubConfig)
    infrastructure: InfrastructureConfig = Field(default_factory=InfrastructureConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)


# ── Config Loading ───────────────────────────────────────────────────

_CONFIG_SEARCH_PATHS = [
    Path("config.yml"),
    Path("config.yaml"),
    Path.home() / ".opsagents" / "config.yml",
    Path.home() / ".opsagents" / "config.yaml",
]


def _find_config_file() -> Path | None:
    """Find the first existing config file from search paths."""
    # Check env var first
    env_path = os.environ.get("OPSAGENTS_CONFIG")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p

    for path in _CONFIG_SEARCH_PATHS:
        if path.exists():
            return path

    return None


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load and parse a YAML config file."""
    with open(path) as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def _apply_env_overrides(data: dict[str, Any]) -> dict[str, Any]:
    """Apply environment variable overrides.

    Environment variables follow the pattern OPSAGENTS_SECTION_KEY.
    For example: OPSAGENTS_LLM_PROVIDER=anthropic
    """
    env_mappings = {
        "OPSAGENTS_LLM_PROVIDER": ("llm", "provider"),
        "OPSAGENTS_LLM_MODEL": ("llm", "model"),
        "OPSAGENTS_LLM_TEMPERATURE": ("llm", "temperature"),
        "OPSAGENTS_LLM_MAX_TOKENS": ("llm", "max_tokens"),
        "OPSAGENTS_APPROVAL_POLICY": ("approval", "default_policy"),
        "OPSAGENTS_AWS_PROFILE": ("aws", "profile"),
        "OPSAGENTS_AWS_REGION": ("aws", "region"),
        "OPSAGENTS_LOG_LEVEL": ("logging", "level"),
        "OPSAGENTS_MCP_TRANSPORT": ("mcp", "transport"),
    }

    for env_key, (section, key) in env_mappings.items():
        value = os.environ.get(env_key)
        if value is not None:
            if section not in data:
                data[section] = {}
            # Convert numeric strings
            if key in ("temperature",):
                data[section][key] = float(value)
            elif key in ("max_tokens",):
                data[section][key] = int(value)
            else:
                data[section][key] = value

    return data


def load_config(
    config_path: str | Path | None = None,
    overrides: dict[str, Any] | None = None,
) -> OpsAgentsConfig:
    """Load configuration from file, env vars, and CLI overrides.

    Args:
        config_path: Explicit path to a config file (highest priority).
        overrides: Dict of override values from CLI flags.

    Returns:
        Fully resolved OpsAgentsConfig instance.
    """
    # Start with empty data (defaults come from Pydantic models)
    data: dict[str, Any] = {}

    # Load from file
    path = Path(config_path) if config_path else _find_config_file()
    if path and path.exists():
        data = _load_yaml(path)

    # Apply env var overrides
    data = _apply_env_overrides(data)

    # Apply CLI overrides
    if overrides:
        for key, value in overrides.items():
            if value is None:
                continue
            parts = key.split(".")
            target = data
            for part in parts[:-1]:
                if part not in target:
                    target[part] = {}
                target = target[part]
            target[parts[-1]] = value

    return OpsAgentsConfig(**data)
