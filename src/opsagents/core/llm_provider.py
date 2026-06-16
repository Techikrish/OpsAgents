"""Multi-provider LLM abstraction.

Factory pattern for creating LLM instances from any supported provider.
Supports automatic fallback to a secondary provider on failure.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

    from opsagents.config import LLMConfig

logger = logging.getLogger(__name__)

# ── Supported Providers ──────────────────────────────────────────────

SUPPORTED_PROVIDERS = {
    "openai",
    "anthropic",
    "google",
    "bedrock",
    "azure",
    "ollama",
}


# ── Provider Factory ─────────────────────────────────────────────────


def _create_openai(model: str, **kwargs: Any) -> BaseChatModel:
    """Create an OpenAI chat model."""
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(model=model, **kwargs)


def _create_anthropic(model: str, **kwargs: Any) -> BaseChatModel:
    """Create an Anthropic chat model."""
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(model=model, **kwargs)


def _create_google(model: str, **kwargs: Any) -> BaseChatModel:
    """Create a Google Generative AI chat model."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(model=model, **kwargs)


def _create_bedrock(model: str, **kwargs: Any) -> BaseChatModel:
    """Create an AWS Bedrock chat model."""
    from langchain_aws import ChatBedrock

    return ChatBedrock(model_id=model, **kwargs)


def _create_azure(model: str, **kwargs: Any) -> BaseChatModel:
    """Create an Azure OpenAI chat model."""
    from langchain_openai import AzureChatOpenAI

    deployment = kwargs.pop("azure_deployment", model)
    api_version = kwargs.pop("azure_api_version", "2024-10-21")
    return AzureChatOpenAI(
        azure_deployment=deployment,
        api_version=api_version,
        **kwargs,
    )


def _create_ollama(model: str, **kwargs: Any) -> BaseChatModel:
    """Create an Ollama (local) chat model."""
    from langchain_ollama import ChatOllama

    base_url = kwargs.pop("base_url", "http://localhost:11434")
    return ChatOllama(model=model, base_url=base_url, **kwargs)


_FACTORY_MAP = {
    "openai": _create_openai,
    "anthropic": _create_anthropic,
    "google": _create_google,
    "bedrock": _create_bedrock,
    "azure": _create_azure,
    "ollama": _create_ollama,
}


# ── Public API ───────────────────────────────────────────────────────


def get_llm(
    provider: str,
    model: str,
    temperature: float = 0.1,
    max_tokens: int = 4096,
    **kwargs: Any,
) -> BaseChatModel:
    """Create an LLM instance for the specified provider.

    Args:
        provider: Provider name (openai, anthropic, google, bedrock, azure, ollama).
        model: Model identifier (e.g. "gpt-4o", "claude-sonnet-4-20250514").
        temperature: Sampling temperature.
        max_tokens: Maximum output tokens.
        **kwargs: Additional provider-specific arguments.

    Returns:
        A LangChain BaseChatModel instance.

    Raises:
        ValueError: If the provider is not supported.
    """
    provider = provider.lower().strip()
    if provider not in _FACTORY_MAP:
        raise ValueError(
            f"Unsupported LLM provider: {provider!r}. "
            f"Supported: {', '.join(sorted(SUPPORTED_PROVIDERS))}"
        )

    factory = _FACTORY_MAP[provider]
    logger.info("Creating LLM: provider=%s model=%s", provider, model)

    return factory(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        **kwargs,
    )


def get_llm_from_config(config: LLMConfig, **kwargs: Any) -> BaseChatModel:
    """Create an LLM instance from an LLMConfig object.

    Args:
        config: LLM configuration from the config file.
        **kwargs: Additional overrides.

    Returns:
        A LangChain BaseChatModel instance.
    """
    extra: dict[str, Any] = {}

    if config.provider == "ollama":
        extra["base_url"] = config.ollama_base_url
    elif config.provider == "azure":
        extra["azure_deployment"] = config.azure_deployment
        extra["azure_api_version"] = config.azure_api_version

    extra.update(kwargs)

    return get_llm(
        provider=config.provider,
        model=config.model,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        **extra,
    )


def get_llm_with_fallback(config: LLMConfig, **kwargs: Any) -> BaseChatModel:
    """Create an LLM with automatic fallback on failure.

    Tries the primary provider first. If it fails during creation,
    falls back to the configured fallback provider.

    Args:
        config: LLM configuration with optional fallback settings.
        **kwargs: Additional overrides.

    Returns:
        A LangChain BaseChatModel instance (primary or fallback).

    Raises:
        RuntimeError: If both primary and fallback providers fail.
    """
    try:
        return get_llm_from_config(config, **kwargs)
    except Exception as primary_err:
        if not config.fallback_provider or not config.fallback_model:
            raise

        logger.warning(
            "Primary LLM failed (%s/%s): %s. Trying fallback (%s/%s).",
            config.provider,
            config.model,
            primary_err,
            config.fallback_provider,
            config.fallback_model,
        )

        try:
            return get_llm(
                provider=config.fallback_provider,
                model=config.fallback_model,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                **kwargs,
            )
        except Exception as fallback_err:
            raise RuntimeError(
                f"Both primary ({config.provider}/{config.model}) and "
                f"fallback ({config.fallback_provider}/{config.fallback_model}) "
                f"LLM providers failed."
            ) from fallback_err
