"""Tests for all Cloud agents."""

from __future__ import annotations

from typing import Any
import pytest

from opsagents.config import OpsAgentsConfig
from opsagents.cloud import (
    InfrastructureAgent,
    SecurityAgent,
    CostAgent,
    IncidentAgent,
    ArchitectureAgent,
)


def test_infrastructure_agent(mock_config: OpsAgentsConfig, mock_llm: Any) -> None:
    """Test InfrastructureAgent initialization and run lifecycle."""
    agent = InfrastructureAgent(config=mock_config, mode="cli")
    assert agent.name == "Infrastructure Provisioner"
    assert "Terraform" in agent.description
    
    state = agent.run("Create an S3 bucket named my-app-data")
    assert state["task"] == "Create an S3 bucket named my-app-data"
    assert len(state["action_plan"]) > 0
    assert state["results"][0].success is True


def test_security_agent(mock_config: OpsAgentsConfig, mock_llm: Any) -> None:
    """Test SecurityAgent initialization and run lifecycle."""
    agent = SecurityAgent(config=mock_config, mode="cli")
    assert agent.name == "Security & Compliance"
    
    state = agent.run("Scan all S3 buckets and IAM policies")
    assert len(state["action_plan"]) > 0
    assert state["results"][0].success is True


def test_cost_agent(mock_config: OpsAgentsConfig, mock_llm: Any) -> None:
    """Test CostAgent initialization and run lifecycle."""
    agent = CostAgent(config=mock_config, mode="cli")
    assert agent.name == "Cost Optimizer"
    
    state = agent.run("Audit unused EBS volumes and suggest savings")
    assert len(state["action_plan"]) > 0
    assert state["results"][0].success is True


def test_incident_agent(mock_config: OpsAgentsConfig, mock_llm: Any) -> None:
    """Test IncidentAgent initialization and run lifecycle."""
    agent = IncidentAgent(config=mock_config, mode="cli")
    assert agent.name == "Incident Response"
    
    state = agent.run("Troubleshoot CloudWatch Alarm CPUUtilization")
    assert len(state["action_plan"]) > 0
    assert state["results"][0].success is True


def test_architecture_agent(mock_config: OpsAgentsConfig, mock_llm: Any) -> None:
    """Test ArchitectureAgent initialization and run lifecycle."""
    agent = ArchitectureAgent(config=mock_config, mode="cli")
    assert agent.name == "Architecture Review"
    
    state = agent.run("Analyze reliability and diagram the active database architecture")
    assert len(state["action_plan"]) > 0
    assert state["results"][0].success is True
