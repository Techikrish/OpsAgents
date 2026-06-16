"""CLI Interface for OpsAgents."""

from __future__ import annotations

import sys
from typing import Any

import click

from opsagents import __version__
from opsagents.config import load_config
from opsagents.core.output import console


@click.group()
@click.option("--config", "-c", type=click.Path(exists=True), help="Path to config.yml")
@click.option("--provider", "-p", help="LLM provider override (e.g. openai, anthropic)")
@click.option("--model", "-m", help="LLM model override (e.g. gpt-4o, claude-3-5-sonnet)")
@click.option("--aws-profile", help="AWS profile override")
@click.option("--aws-region", help="AWS region override")
@click.pass_context
def cli(
    ctx: click.Context,
    config: str | None,
    provider: str | None,
    model: str | None,
    aws_profile: str | None,
    aws_region: str | None,
) -> None:
    """OpsAgents — Production-ready Cloud & DevOps AI Agents."""
    overrides: dict[str, Any] = {}
    if provider:
        overrides["llm.provider"] = provider
    if model:
        overrides["llm.model"] = model
    if aws_profile:
        overrides["aws.profile"] = aws_profile
    if aws_region:
        overrides["aws.region"] = aws_region

    try:
        ctx.obj = load_config(config_path=config, overrides=overrides)
    except Exception as e:
        console.print(f"[red]Error loading configuration: {e}[/red]")
        sys.exit(1)


@cli.command()
def version() -> None:
    """Show the version info."""
    click.echo(f"OpsAgents v{__version__}")


# ── Cloud Agents Commands ───────────────────────────────────────────


@cli.command()
@click.argument("task")
@click.pass_obj
def infra(config: Any, task: str) -> None:
    """Infrastructure Provisioner Agent (Terraform / CloudFormation)."""
    from opsagents.cloud import InfrastructureAgent
    agent = InfrastructureAgent(config=config, mode="cli")
    agent.run(task)


@cli.command()
@click.argument("task")
@click.pass_obj
def security(config: Any, task: str) -> None:
    """Security & Compliance Agent."""
    from opsagents.cloud import SecurityAgent
    agent = SecurityAgent(config=config, mode="cli")
    agent.run(task)


@cli.command()
@click.argument("task")
@click.pass_obj
def cost(config: Any, task: str) -> None:
    """Cost Optimizer Agent."""
    from opsagents.cloud import CostAgent
    agent = CostAgent(config=config, mode="cli")
    agent.run(task)


@cli.command()
@click.argument("task")
@click.pass_obj
def incident(config: Any, task: str) -> None:
    """Incident Response Agent."""
    from opsagents.cloud import IncidentAgent
    agent = IncidentAgent(config=config, mode="cli")
    agent.run(task)


@cli.command()
@click.argument("task")
@click.pass_obj
def architect(config: Any, task: str) -> None:
    """Architecture Review Agent."""
    from opsagents.cloud import ArchitectureAgent
    agent = ArchitectureAgent(config=config, mode="cli")
    agent.run(task)


# ── DevOps Agents Commands ──────────────────────────────────────────


@cli.command()
@click.argument("task")
@click.pass_obj
def cicd(config: Any, task: str) -> None:
    """CI/CD Pipeline Agent."""
    from opsagents.devops import CICDAgent
    agent = CICDAgent(config=config, mode="cli")
    agent.run(task)


@cli.command()
@click.argument("task")
@click.pass_obj
def k8s(config: Any, task: str) -> None:
    """Kubernetes Operations Agent."""
    from opsagents.devops import KubernetesAgent
    agent = KubernetesAgent(config=config, mode="cli")
    agent.run(task)


@cli.command()
@click.argument("task")
@click.pass_obj
def monitor(config: Any, task: str) -> None:
    """Monitoring & Observability Agent."""
    from opsagents.devops import MonitoringAgent
    agent = MonitoringAgent(config=config, mode="cli")
    agent.run(task)


@cli.command()
@click.argument("task")
@click.pass_obj
def gitops(config: Any, task: str) -> None:
    """GitOps & Release Agent."""
    from opsagents.devops import GitOpsAgent
    agent = GitOpsAgent(config=config, mode="cli")
    agent.run(task)


@cli.command()
@click.argument("task")
@click.pass_obj
def container(config: Any, task: str) -> None:
    """Container & Image Security Agent."""
    from opsagents.devops import ContainerSecurityAgent
    agent = ContainerSecurityAgent(config=config, mode="cli")
    agent.run(task)


# ── Utility Commands ────────────────────────────────────────────────


@cli.command()
@click.pass_obj
def mcp(config: Any) -> None:
    """Start the MCP server to integrate with coding agents (Cursor, Claude Code)."""
    from opsagents.mcp.server import run_mcp_server
    run_mcp_server(config)


if __name__ == "__main__":
    cli()
