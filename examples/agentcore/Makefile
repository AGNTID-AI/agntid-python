.PHONY: setup prepare test validate package dev deploy

SDK_ROOT := ../..
AGENT_PROJECT := app/AgntidAgent
AGENT_PYTHON := $(AGENT_PROJECT)/.venv/bin/python
SDK_WHEEL := app/AgntidAgent/vendor/agntid_sdk-0.2.0-py3-none-any.whl
SDK_SOURCES := $(shell find $(SDK_ROOT)/src/agntid -type f)

setup: prepare

prepare: $(SDK_WHEEL)

$(SDK_WHEEL): $(SDK_ROOT)/pyproject.toml $(SDK_SOURCES)
	mkdir -p $(dir $(SDK_WHEEL))
	uv build $(SDK_ROOT) --wheel --out-dir $(dir $(SDK_WHEEL))
	test -f $(SDK_WHEEL)

test: prepare
	uv sync --project $(AGENT_PROJECT) --extra dev --locked --no-install-package agntid-sdk
	uv pip install --python $(AGENT_PYTHON) --no-deps --reinstall $(SDK_WHEEL)
	uv run --project $(AGENT_PROJECT) --no-sync pytest -q

validate: prepare
	agentcore validate --directory .

package: prepare
	agentcore package --directory . --runtime AgntidAgent

dev: prepare
	agentcore dev --logs --skip-deploy

deploy: prepare
	agentcore deploy
