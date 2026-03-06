# agntid-sdk Makefile
# Build, test, and release the AgntID Python SDK.

.PHONY: help build clean install install-dev setup-dev test lint version

PYTHON ?= python3
VERSION := $(shell $(PYTHON) -c "import re; print(re.search(r'version\s*=\s*\"([^\"]+)\"', open('pyproject.toml').read()).group(1))")

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-16s\033[0m %s\n", $$1, $$2}'

version: ## Print current SDK version
	@echo "agntid-sdk $(VERSION)"

build: clean ## Build sdist and wheel into dist/
	@echo "Building agntid-sdk $(VERSION) ..."
	$(PYTHON) -m build --outdir dist/
	@echo ""
	@echo "Artifacts:"
	@ls -lh dist/
	@echo ""
	@echo "Build complete: agntid-sdk $(VERSION)"

clean: ## Remove build artifacts
	rm -rf dist/ build/ src/*.egg-info src/agntid_sdk.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

install: ## Install the SDK (editable mode)
	$(PYTHON) -m pip install -e .

install-dev: ## Install with dev + msk extras (editable)
	$(PYTHON) -m pip install -e ".[dev,msk]"

setup-dev: ## Create .venv and install SDK with all extras
	@./scripts/setup-dev.sh

test: ## Run unit tests
	$(PYTHON) -m pytest tests/ -v

lint: ## Run basic lint checks
	$(PYTHON) -m py_compile src/agntid/__init__.py
	@echo "Syntax OK"
