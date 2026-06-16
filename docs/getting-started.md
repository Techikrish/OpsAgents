# Getting Started

Follow this guide to get OpsAgents installed and running on your local machine.

## Requirements

- Python 3.11 or higher
- Optional: AWS CLI configured with credentials
- Optional: local kubeconfig configured for Kubernetes agent operations

## Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/opsagents/opsagents.git
   cd opsagents
   ```

2. Setup virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```

3. Setup environment configuration:
   ```bash
   cp .env.example .env
   # Add your API keys to the .env file
   ```

## Running Your First Task

Use the CLI command router to execute an agent:
```bash
opsagents security "Scan all security groups for public port access"
```

The agent will load, scan security groups, compile recommendations, and present them in a formatted table before asking for confirmation.
