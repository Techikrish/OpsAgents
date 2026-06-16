"""Tests for the MCP server tools registration."""

from __future__ import annotations

import pytest

from opsagents.mcp.server import mcp


@pytest.mark.asyncio
async def test_mcp_tools_registration() -> None:
    """Verify that all agents and the resume utility are registered as MCP tools."""
    # Retrieve names of all registered tools
    tools = await mcp.list_tools()
    registered_tools = [tool.name for tool in tools]
    
    expected_tools = [
        "run_infra_agent",
        "run_security_agent",
        "run_cost_agent",
        "run_incident_agent",
        "run_architect_agent",
        "run_cicd_agent",
        "run_k8s_agent",
        "run_monitor_agent",
        "run_gitops_agent",
        "run_container_agent",
        "resume_agent",
    ]
    
    for tool_name in expected_tools:
        assert tool_name in registered_tools, f"Tool {tool_name} was not registered on FastMCP server"
        
    # Check that there are at least 11 registered tools
    assert len(registered_tools) >= 11
