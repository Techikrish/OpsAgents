.PHONY: help install dev lint format typecheck test test-cov clean docker-build docker-run mcp

# ── Default ──────────────────────────────────────────────────────────
help: ## Show this help message
	@echo "OpsAgents — Cloud & DevOps AI Agents"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

# ── Setup ────────────────────────────────────────────────────────────
install: ## Install dependencies
	uv sync

dev: ## Install with dev dependencies
	uv sync --extra dev

# ── Quality ──────────────────────────────────────────────────────────
lint: ## Run linter (ruff)
	uv run ruff check src/ tests/

format: ## Format code (ruff)
	uv run ruff format src/ tests/

format-check: ## Check formatting without changes
	uv run ruff format --check src/ tests/

typecheck: ## Run type checker (mypy)
	uv run mypy src/opsagents/

# ── Testing ──────────────────────────────────────────────────────────
test: ## Run tests
	uv run pytest tests/ -v

test-cov: ## Run tests with coverage
	uv run pytest tests/ -v --cov=opsagents --cov-report=html --cov-report=term

# ── Docker ───────────────────────────────────────────────────────────
docker-build: ## Build Docker image
	docker build -t opsagents:latest .

docker-run: ## Run via Docker Compose
	docker compose up

# ── MCP ──────────────────────────────────────────────────────────────
mcp: ## Start MCP server (stdio)
	uv run opsagents mcp

# ── Cleanup ──────────────────────────────────────────────────────────
clean: ## Remove build artifacts
	rm -rf dist/ build/ *.egg-info .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
