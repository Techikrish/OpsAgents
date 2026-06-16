"""Tool utilities and decorators for agent tools.

Provides common patterns for wrapping tool functions with error
handling, output formatting, and subprocess execution.
"""

from __future__ import annotations

import functools
import json
import logging
import subprocess
from collections.abc import Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


# ── Safe Tool Decorator ──────────────────────────────────────────────


def safe_tool(func: F) -> F:
    """Decorator that wraps a tool function with error handling.

    Catches exceptions and returns structured error messages instead
    of crashing the agent graph. Also logs tool invocations.

    Usage:
        @safe_tool
        @tool
        def my_tool(arg: str) -> str:
            ...
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        tool_name = func.__name__
        logger.debug("Tool invoked: %s (args=%s, kwargs=%s)", tool_name, args, kwargs)
        try:
            result = func(*args, **kwargs)
            logger.debug("Tool %s succeeded", tool_name)
            return result
        except Exception as e:
            error_msg = f"Tool '{tool_name}' failed: {type(e).__name__}: {e}"
            logger.error(error_msg, exc_info=True)
            return format_tool_error(tool_name, e)

    return wrapper  # type: ignore[return-value]


# ── Output Formatting ────────────────────────────────────────────────


def format_tool_result(
    tool_name: str,
    data: Any,
    summary: str = "",
) -> str:
    """Format a tool result for LLM consumption.

    Args:
        tool_name: Name of the tool that produced the result.
        data: Result data (dict, list, or string).
        summary: Optional human-readable summary.

    Returns:
        Formatted string suitable for inclusion in LLM messages.
    """
    parts = [f"## Tool Result: {tool_name}"]

    if summary:
        parts.append(f"\n{summary}")

    if isinstance(data, (dict, list)):
        parts.append(f"\n```json\n{json.dumps(data, indent=2, default=str)}\n```")
    elif isinstance(data, str):
        parts.append(f"\n{data}")
    else:
        parts.append(f"\n{data!r}")

    return "\n".join(parts)


def format_tool_error(tool_name: str, error: Exception) -> str:
    """Format a tool error for LLM consumption.

    Args:
        tool_name: Name of the tool that failed.
        error: The exception that occurred.

    Returns:
        Formatted error string.
    """
    return (
        f"## Tool Error: {tool_name}\n\n"
        f"**Error Type:** {type(error).__name__}\n"
        f"**Message:** {error}\n\n"
        f"Please analyze this error and decide how to proceed."
    )


# ── Command Execution ────────────────────────────────────────────────


def run_command(
    command: list[str],
    cwd: str | None = None,
    timeout: int = 300,
    capture_output: bool = True,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Execute a shell command safely.

    Args:
        command: Command and arguments as a list.
        cwd: Working directory.
        timeout: Timeout in seconds.
        capture_output: Whether to capture stdout/stderr.
        env: Additional environment variables.

    Returns:
        Dict with keys: returncode, stdout, stderr, command.
    """
    import os

    full_env = {**os.environ, **(env or {})}

    logger.info("Running command: %s (cwd=%s)", " ".join(command), cwd)

    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            timeout=timeout,
            capture_output=capture_output,
            text=True,
            env=full_env,
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout or "",
            "stderr": result.stderr or "",
            "command": " ".join(command),
            "success": result.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": f"Command timed out after {timeout}s",
            "command": " ".join(command),
            "success": False,
        }
    except FileNotFoundError:
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": f"Command not found: {command[0]}",
            "command": " ".join(command),
            "success": False,
        }


# ── AWS Helpers ──────────────────────────────────────────────────────


def get_boto3_session(
    profile: str | None = None,
    region: str | None = None,
) -> Any:
    """Create a boto3 session with the given profile and region.

    Args:
        profile: AWS profile name (from ~/.aws/credentials).
        region: AWS region name.

    Returns:
        boto3.Session instance.
    """
    import boto3

    kwargs: dict[str, Any] = {}
    if profile:
        kwargs["profile_name"] = profile
    if region:
        kwargs["region_name"] = region

    return boto3.Session(**kwargs)


def get_boto3_client(
    service: str,
    profile: str | None = None,
    region: str | None = None,
) -> Any:
    """Create a boto3 client for the specified AWS service.

    Args:
        service: AWS service name (e.g., "ec2", "s3", "iam").
        profile: AWS profile name.
        region: AWS region name.

    Returns:
        boto3 service client.
    """
    session = get_boto3_session(profile=profile, region=region)
    return session.client(service)
