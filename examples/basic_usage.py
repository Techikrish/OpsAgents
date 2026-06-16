"""Example showing programmatic usage of OpsAgents."""

from __future__ import annotations

import os
from opsagents.config import load_config
from opsagents.cloud import SecurityAgent


def main() -> None:
    # Ensure OPENAI_API_KEY is available (using dummy for demonstration if not set)
    if "OPENAI_API_KEY" not in os.environ:
        os.environ["OPENAI_API_KEY"] = "dummy-key"
        print("OPENAI_API_KEY not found. Using dummy key for showcase.")

    # Load configuration
    config = load_config(
        overrides={
            "llm.provider": "openai",
            "llm.model": "gpt-4o",
            "approval.default_policy": "auto",  # auto-approve during showcase runs
        }
    )

    print("Initializing Security & Compliance Agent...")
    agent = SecurityAgent(config=config, mode="cli")

    # Define a task
    task = "Scan all S3 buckets for public access"

    print(f"Running agent on task: '{task}'")
    state = agent.run(task)

    print("\n--- Final Run Report ---")
    print(state.get("final_report"))


if __name__ == "__main__":
    main()
