"""Tests for all DevOps agents."""

from __future__ import annotations

from typing import Any
import pytest

from opsagents.config import OpsAgentsConfig
from opsagents.devops import (
    CICDAgent,
    KubernetesAgent,
    MonitoringAgent,
    GitOpsAgent,
    ContainerSecurityAgent,
)


def test_cicd_agent(mock_config: OpsAgentsConfig, mock_llm: Any) -> None:
    """Test CICDAgent initialization and run lifecycle."""
    agent = CICDAgent(config=mock_config, mode="cli")
    assert agent.name == "CI/CD Pipeline"
    
    state = agent.run("Generate a github workflow for python project")
    assert state["task"] == "Generate a github workflow for python project"
    assert len(state["action_plan"]) > 0
    assert state["results"][0].success is True


def test_kubernetes_agent(mock_config: OpsAgentsConfig, mock_llm: Any) -> None:
    """Test KubernetesAgent initialization and run lifecycle."""
    agent = KubernetesAgent(config=mock_config, mode="cli")
    assert agent.name == "Kubernetes Operations"
    
    state = agent.run("Troubleshoot failing pod api-server-5f99")
    assert len(state["action_plan"]) > 0
    assert state["results"][0].success is True


def test_monitoring_agent(mock_config: OpsAgentsConfig, mock_llm: Any) -> None:
    """Test MonitoringAgent initialization and run lifecycle."""
    agent = MonitoringAgent(config=mock_config, mode="cli")
    assert agent.name == "Monitoring & Observability"
    
    state = agent.run("Setup alerts and a Grafana dashboard for web service")
    assert len(state["action_plan"]) > 0
    assert state["results"][0].success is True


def test_gitops_agent(mock_config: OpsAgentsConfig, mock_llm: Any) -> None:
    """Test GitOpsAgent initialization and run lifecycle."""
    agent = GitOpsAgent(config=mock_config, mode="cli")
    assert agent.name == "GitOps & Release"
    
    state = agent.run("Configure an ArgoCD app for deployment manifests")
    assert len(state["action_plan"]) > 0
    assert state["results"][0].success is True


def test_container_security_agent(mock_config: OpsAgentsConfig, mock_llm: Any) -> None:
    """Test ContainerSecurityAgent initialization and run lifecycle."""
    agent = ContainerSecurityAgent(config=mock_config, mode="cli")
    assert agent.name == "Container & Image Security"
    
    state = agent.run("Scan container image alpine:3.18 for vulnerabilities")
    assert len(state["action_plan"]) > 0
    assert state["results"][0].success is True
