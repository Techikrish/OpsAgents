"""Tools for the CI/CD Pipeline Agent."""

from __future__ import annotations

import json
import logging
import os

import yaml
from langchain_core.tools import tool

from opsagents.core.tools import format_tool_result

logger = logging.getLogger(__name__)


@tool
def analyze_repository(repo_path: str = ".") -> str:
    """Analyze the repository directory to detect language, build system, and dependencies.

    Args:
        repo_path: Path to the repository.
    """
    try:
        abs_path = os.path.abspath(repo_path)
        if not os.path.exists(abs_path):
            return format_tool_result("analyze_repository", {"error": f"Path '{repo_path}' does not exist."})

        files = os.listdir(abs_path)
        detected_languages = []
        build_system = "Unknown"
        frameworks = []

        # Simple heuristic detection
        if "package.json" in files:
            detected_languages.append("JavaScript/TypeScript")
            build_system = "npm/yarn/pnpm"
            try:
                with open(os.path.join(abs_path, "package.json")) as f:
                    pkg = json.load(f)
                    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                    if "next" in deps:
                        frameworks.append("Next.js")
                    if "react" in deps:
                        frameworks.append("React")
                    if "express" in deps:
                        frameworks.append("Express")
            except Exception:
                pass

        if "pyproject.toml" in files or "requirements.txt" in files or "setup.py" in files:
            detected_languages.append("Python")
            if "pyproject.toml" in files:
                build_system = "poetry/pipenv/uv"
            elif "requirements.txt" in files:
                build_system = "pip"
            else:
                build_system = "setuptools"

        if "pom.xml" in files:
            detected_languages.append("Java")
            build_system = "Maven"
        elif "build.gradle" in files or "build.gradle.kts" in files:
            detected_languages.append("Java/Kotlin")
            build_system = "Gradle"

        if "go.mod" in files:
            detected_languages.append("Go")
            build_system = "Go Modules"

        if "Cargo.toml" in files:
            detected_languages.append("Rust")
            build_system = "Cargo"

        if "Dockerfile" in files:
            frameworks.append("Docker")

        if not detected_languages:
            detected_languages.append("Unknown")

        return format_tool_result("analyze_repository", {
            "path": abs_path,
            "languages": detected_languages,
            "build_system": build_system,
            "frameworks": frameworks,
            "has_github_workflows": os.path.exists(os.path.join(abs_path, ".github/workflows"))
        })
    except Exception as e:
        return format_tool_result("analyze_repository", {"error": str(e)})


@tool
def generate_github_actions(
    lang: str,
    build_system: str,
    output_path: str = ".github/workflows/ci.yml",
) -> str:
    """Generate a high-quality GitHub Actions CI/CD template.

    Args:
        lang: Language of the project (e.g. python, node, go).
        build_system: Build system (e.g. uv, npm, maven, cargo).
        output_path: Output file path.
    """
    try:
        lang_lower = lang.lower()
        bs_lower = build_system.lower()

        # Simple boilerplate generation based on parameters
        if "python" in lang_lower:
            if "uv" in bs_lower:
                content = """name: Python CI

on:
  push:
    branches: [ main, master ]
  pull_request:
    branches: [ main, master ]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install uv
        uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version-file: "pyproject.toml"
      - name: Install dependencies
        run: uv sync --all-groups
      - name: Lint with ruff
        run: uv run ruff check .
      - name: Run tests
        run: uv run pytest tests/
"""
            else:
                content = """name: Python CI

on:
  push:
    branches: [ main, master ]
  pull_request:
    branches: [ main, master ]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
          if [ -f requirements-dev.txt ]; then pip install -r requirements-dev.txt; fi
      - name: Run tests
        run: pytest
"""
        elif "node" in lang_lower or "javascript" in lang_lower or "typescript" in lang_lower:
            content = f"""name: Node.js CI

on:
  push:
    branches: [ main, master ]
  pull_request:
    branches: [ main, master ]

jobs:
  build-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Use Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: '{'yarn' if 'yarn' in bs_lower else 'npm'}'
      - name: Install dependencies
        run: {'yarn install --frozen-lockfile' if 'yarn' in bs_lower else 'npm ci'}
      - name: Run build
        run: {'yarn build' if 'yarn' in bs_lower else 'npm run build --if-present'}
      - name: Run tests
        run: {'yarn test' if 'yarn' in bs_lower else 'npm test'}
"""
        else:
            content = """name: Generic CI

on:
  push:
    branches: [ main, master ]
  pull_request:
    branches: [ main, master ]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build
        run: echo "Build started"
"""

        # Make directory if not exists
        dir_name = os.path.dirname(output_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        with open(output_path, "w") as f:
            f.write(content)

        return format_tool_result("generate_github_actions", {
            "output_path": output_path,
            "status": "created",
            "content": content
        })
    except Exception as e:
        return format_tool_result("generate_github_actions", {"error": str(e)})


@tool
def validate_workflow(workflow_path: str) -> str:
    """Validate a CI/CD workflow YAML structure and syntax.

    Args:
        workflow_path: Path to the workflow file.
    """
    try:
        if not os.path.exists(workflow_path):
            return format_tool_result("validate_workflow", {"error": f"File '{workflow_path}' not found."})

        with open(workflow_path) as f:
            data = yaml.safe_load(f)

        findings = []
        if not data:
            findings.append("Workflow file is empty.")
        else:
            if "name" not in data:
                findings.append("Missing 'name' field in workflow.")
            if "on" not in data:
                findings.append("Missing trigger 'on' field in workflow.")
            if "jobs" not in data or not isinstance(data["jobs"], dict):
                findings.append("Missing or invalid 'jobs' dictionary in workflow.")
            else:
                for job_name, job in data["jobs"].items():
                    if "runs-on" not in job:
                        findings.append(f"Job '{job_name}' is missing 'runs-on' target.")
                    if "steps" not in job or not isinstance(job["steps"], list):
                        findings.append(f"Job '{job_name}' has missing or invalid 'steps' list.")

        return format_tool_result("validate_workflow", {
            "file": workflow_path,
            "valid": len(findings) == 0,
            "errors": findings
        })
    except Exception as e:
        return format_tool_result("validate_workflow", {"error": str(e)})


@tool
def optimize_pipeline(workflow_path: str) -> str:
    """Read a workflow file and suggest pipeline performance and security optimizations.

    Args:
        workflow_path: Path to the workflow file.
    """
    try:
        if not os.path.exists(workflow_path):
            return format_tool_result("optimize_pipeline", {"error": f"File '{workflow_path}' not found."})

        with open(workflow_path) as f:
            content = f.read()

        suggestions = []
        if "checkout@v4" not in content and "checkout@v" in content:
            suggestions.append({
                "type": "version",
                "finding": "Using old checkout action version",
                "recommendation": "Upgrade actions/checkout to v4 for Node 20 runtime support."
            })
        if "cache" not in content:
            suggestions.append({
                "type": "performance",
                "finding": "No package manager caching detected",
                "recommendation": "Use setup-python/setup-node default caching options to speed up run time."
            })
        if "permissions" not in content:
            suggestions.append({
                "type": "security",
                "finding": "Implicit workflow permissions",
                "recommendation": "Add top-level read-only permissions block to prevent credential leakage: 'permissions: read-all'."
            })

        return format_tool_result("optimize_pipeline", {
            "file": workflow_path,
            "suggestions": suggestions
        })
    except Exception as e:
        return format_tool_result("optimize_pipeline", {"error": str(e)})


@tool
def list_workflow_runs(repo: str = "") -> str:
    """Get a summary of recent workflow runs.

    Args:
        repo: Repository name (optional).
    """
    # Simulate list of workflow runs
    runs = [
        {"id": "1098234", "name": "Python CI", "event": "push", "status": "completed", "conclusion": "failure", "duration": "4m 12s", "branch": "main"},
        {"id": "1098012", "name": "Linter", "event": "pull_request", "status": "completed", "conclusion": "success", "duration": "1m 5s", "branch": "patch-1"},
        {"id": "1097821", "name": "Build Image", "event": "push", "status": "completed", "conclusion": "success", "duration": "8m 42s", "branch": "main"}
    ]
    return format_tool_result("list_workflow_runs", {
        "repository": repo or "current",
        "runs": runs
    })


@tool
def debug_pipeline_failure(run_id: str) -> str:
    """Fetch logs for a failed workflow run to identify the failure root cause.

    Args:
        run_id: ID of the failed workflow run.
    """
    # Mock log output for troubleshooting
    log_output = (
        "Run pytest tests/\n"
        "============================= test session starts =============================\n"
        "platform linux -- Python 3.11.2, pytest-7.2.1, pluggy-1.0.0\n"
        "rootdir: /home/runner/work/opsagents/opsagents\n"
        "collected 15 items\n\n"
        "tests/core/test_base_agent.py ..F......F....\n"
        "================================== FAILURES ===================================\n"
        "____________________ test_agent_graph_execution _____________________\n"
        "tests/core/test_base_agent.py:42: in test_agent_graph_execution\n"
        "    assert state[\"approval_response\"] == \"approve\"\n"
        "E   KeyError: 'approval_response'\n"
        "=========================== short test summary info ===========================\n"
        "FAILED tests/core/test_base_agent.py::test_agent_graph_execution\n"
        "========================= 1 failed, 14 passed in 4.31s ========================"
    )
    return format_tool_result("debug_pipeline_failure", {
        "run_id": run_id,
        "failed_step": "Run pytest tests/",
        "exit_code": 1,
        "logs": log_output
    })


def get_cicd_tools() -> list:
    """Return all CI/CD tools."""
    return [
        analyze_repository,
        generate_github_actions,
        validate_workflow,
        optimize_pipeline,
        list_workflow_runs,
        debug_pipeline_failure
    ]
