# Contributing to OpsAgents

Thank you for your interest in contributing to OpsAgents! We welcome contributions of all forms, including bug reports, feature requests, documentation, and pull requests.

## Development Workflow

1. Fork the repository and create your branch from `main`:
   ```bash
   git checkout -b feature/my-new-feature
   ```

2. Set up development dependencies:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```

3. Make code modifications and run local verification checks:
   ```bash
   # Run type checks
   make typecheck

   # Run format checks
   make format-check

   # Run test suite
   make test
   ```

4. Commit your changes. Ensure your commit messages are descriptive and conform to standard conventions.

5. Submit a Pull Request. Provide a clear explanation of what was changed and links to any related issue tracking.

## Code of Conduct

Please maintain professional, respectful communication at all times.
