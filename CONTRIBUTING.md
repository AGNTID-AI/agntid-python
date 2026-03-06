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

## Creating a release

### Test the release (GitHub only)

You can test the release workflow without PyPI:

1. Ensure the release workflow and version are committed and pushed to `main`.
2. Create and push a tag (e.g. first release):
   ```bash
   git tag v0.1.0
   git push origin v0.1.0
   ```
3. Open **Actions** on the repo and watch the **Release** workflow run. The **Publish to PyPI** step may show as failed (red) if `PYPI_API_TOKEN` is not set — that’s expected; the job still succeeds.
4. Open **Releases** — you should see **v0.1.0** with the wheel and sdist attached. Install with:
   ```bash
   pip install https://github.com/AGNTID-AI/agntid-python/releases/download/v0.1.0/agntid_sdk-0.1.0-py3-none-any.whl
   ```

### Cut a release

Maintainers: to publish a release (e.g. v0.1.0), ensure the version in `pyproject.toml` and `src/agntid/__init__.py` is updated, then push a tag:

```bash
git tag v0.1.0
git push origin v0.1.0
```

The [Release workflow](.github/workflows/release.yml) will:

1. Build the wheel and sdist
2. **Publish to PyPI** (if `PYPI_API_TOKEN` is set; see below)
3. Create a GitHub Release and attach the built artifacts

Users can then install with:

```bash
# From PyPI (after the first release and once PyPI is configured)
pip install agntid-sdk

# Or from GitHub Release
pip install https://github.com/AGNTID-AI/agntid-python/releases/download/v0.1.0/agntid_sdk-0.1.0-py3-none-any.whl
```

### Publishing to PyPI

1. Reserve the project name on PyPI if needed: the package is published as `agntid-sdk` (see `pyproject.toml`). Create the project at [pypi.org](https://pypi.org) so the name is yours.
2. Create a PyPI account at [pypi.org](https://pypi.org/account/register/) (and [test.pypi.org](https://test.pypi.org/) for testing).
3. Create an API token: [pypi.org/manage/account/token](https://pypi.org/manage/account/token/) (scope: entire account or just this project).
4. Add the token as a repository secret in this repo: **Settings → Secrets and variables → Actions → New repository secret** → name `PYPI_API_TOKEN`, value = the token.

After that, each release (tag push) will upload the package to PyPI. If `PYPI_API_TOKEN` is not set, the PyPI upload will fail; the workflow still completes and creates the GitHub Release.

Thanks for contributing.
