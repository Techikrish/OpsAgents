"""Shared fixtures and mocks for pytest."""

from __future__ import annotations

from unittest.mock import MagicMock
import pytest

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage

from opsagents.config import load_config, OpsAgentsConfig


@pytest.fixture
def mock_config() -> OpsAgentsConfig:
    """Return a mock OpsAgentsConfig configuration object."""
    return load_config(
        overrides={
            "llm.provider": "openai",
            "llm.model": "gpt-4o",
            "aws.profile": "mock-profile",
            "aws.region": "us-east-1",
            "approval.default_policy": "auto",
            "approval.risk_levels.low": "auto",
            "approval.risk_levels.medium": "auto",
            "approval.risk_levels.high": "auto",
            "approval.risk_levels.critical": "auto",
        }
    )



@pytest.fixture
def mock_llm(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Mock get_llm_with_fallback to return a dummy LLM."""
    mock_chat = MagicMock(spec=BaseChatModel)
    
    # Mock invoke return value
    mock_message = AIMessage(content="Mock LLM Response details")
    mock_chat.invoke.return_value = mock_message
    
    # Mock bind_tools behavior
    mock_chat.bind_tools.return_value = mock_chat

    # Monkeypatch the provider loading logic in both base_agent and llm_provider
    import opsagents.core.base_agent
    import opsagents.core.llm_provider
    
    monkeypatch.setattr(
        opsagents.core.base_agent,
        "get_llm_with_fallback",
        lambda *args, **kwargs: mock_chat
    )
    monkeypatch.setattr(
        opsagents.core.llm_provider,
        "get_llm_with_fallback",
        lambda *args, **kwargs: mock_chat
    )

    return mock_chat
