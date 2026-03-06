# Contributing to AgntID Python SDK

Thank you for your interest in contributing. This document gives a short overview of how to get started.

## How to contribute

- **Bug reports and feature requests** — Open an [issue](https://github.com/AGNTID-AI/agntid-python/issues) with a clear description and steps to reproduce (for bugs).
- **Code changes** — Open a pull request (PR) from a branch. We’ll review and merge when ready.

## Development setup

1. **Clone the repo**

   ```bash
   git clone https://github.com/AGNTID-AI/agntid-python.git
   cd agntid-python
   ```

2. **Create a virtual environment and install in editable mode**

   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -e ".[dev,mcp,msk]"
   ```

   Or use the setup script:

   ```bash
   ./scripts/setup-dev.sh
   source .venv/bin/activate
   ```

3. **Run tests**

   ```bash
   make test
   # or
   pytest
   ```

## Code and commit guidelines

- **Python** — Use Python 3.10+ style. The project is typed; keep type hints on public APIs.
- **Style** — Format with Black, sort imports with isort. Run `make lint` or your usual formatter before committing.
- **Commits** — Use clear, present-tense messages (e.g. `Add X`, `Fix Y`). Reference issues in the message or PR description when relevant.

## Pull request process

1. Create a branch from `main` (e.g. `fix/issue-123` or `feat/add-xyz`).
2. Make your changes and add or update tests as needed.
3. Ensure tests pass and, if applicable, lint/format checks pass.
4. Open a PR against `main` with a short description of the change.
5. Address review feedback. Once approved, a maintainer will merge.

## Questions

If you have questions that don’t fit an issue or PR, you can reach out via the contact details on [agntid.ai](https://agntid.ai).

Thanks for contributing.
