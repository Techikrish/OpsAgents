# OpsAgents — Production-Ready Cloud & DevOps AI Agents

[![CI](https://github.com/Techikrish/OpsAgents/actions/workflows/ci.yml/badge.svg)](https://github.com/Techikrish/OpsAgents/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](https://www.python.org/)

> ⚠️ **BETA NOTICE**: This project is currently in beta. Do not use in production environments. Breaking changes may occur without notice. Use at your own risk.

OpsAgents is a production-ready suite of 10 intelligent AI agents (5 Cloud + 5 DevOps) built with **LangGraph** and Python. It provides cloud and DevOps engineers with automated assistance for daily tasks under a **Human-in-the-Loop** model.

It runs locally as a command-line interface (CLI) or integrates directly into coding agents (such as Claude Code, Cursor, Antigravity, Codex, or OpenCode) via the **Model Context Protocol (MCP)**.

---

## Agent Suite

### Cloud Agents
1. **Infrastructure Provisioner**: Generates, validates, and provisions Terraform/CloudFormation templates.
2. **Security & Compliance**: Scans S3 bucket properties, EC2 security groups, IAM policy definitions, and CIS controls.
3. **Cost Optimizer**: Audits unused EC2 resources, rightsizes configurations, and optimizes cost structures.
4. **Incident Response**: Diagnoses active CloudWatch metric/log alerts and runs auto-remediations.
5. **Architecture Review**: Discovers inventory configurations, audits reliability metrics, and generates Mermaid architectural layouts.

### DevOps Agents
1. **CI/CD Pipeline**: Audits repository language setups and structures optimized pipeline workflows.
2. **Kubernetes Operations**: Checks cluster statuses, logs, scales replicas, and troubleshoots failing pods.
3. **Monitoring & Observability**: Configures Prometheus alert rules, Alertmanager routing, and Grafana dashboards.
4. **GitOps & Release**: Configures ArgoCD Application CRDs, Canary rollout sequences, and semver tag bumps.
5. **Container & Image Security**: Runs Trivy image vulnerability assessments, scans lockfiles, and audits Dockerfile security.

---

## Installation & Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/opsagents/opsagents.git
   cd opsagents
   ```

2. Create virtual environment and install package dependencies:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```

3. Configure environment credentials:
   ```bash
   cp .env.example .env
   # Edit .env with your LLM provider keys and AWS credentials
   ```

---

## Quickstart

### Running CLI Mode
```bash
# Run Infrastructure Provisioner
opsagents infra "Create a VPC with public and private subnets in us-east-1"

# Run Kubernetes Operations
opsagents k8s "Troubleshoot pod backend-service-abcd in namespace default"

# Run Security & Compliance
opsagents security "Scan all security groups for public SSH access"
```

### Running MCP Mode
Start the MCP server to connect with Cursor, Claude Code, etc.:
```bash
opsagents mcp
```

Refer to the [MCP Integration Guide](docs/mcp-integration.md) to register tools in your IDE settings.

---

## Development & Verification

Convenient lifecycle commands are provided via the `Makefile`:

```bash
# Run style and format checks
make lint
make format-check

# Run static type checks
make typecheck

# Run test suite
make test
```

## License
Licensed under the [Apache License, Version 2.0](LICENSE).
