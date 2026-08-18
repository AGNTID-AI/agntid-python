.PHONY: sync test direct-allow direct-deny identity langchain-smoke deepagents-smoke delegation-smoke engineering-demo ops-chat

sync:
	uv sync --extra dev --python 3.11

test:
	uv run pytest -q

direct-allow:
	uv run agntid-poc direct --first 11 --second 22

direct-deny:
	uv run agntid-poc direct --first 11 --second 32

identity:
	uv run agntid-poc identity-matrix

langchain-smoke:
	uv run agntid-poc framework-smoke --framework langchain

deepagents-smoke:
	uv run agntid-poc framework-smoke --framework deepagents

delegation-smoke:
	uv run agntid-poc --agent-id service-operations-supervisor:v1 --user-id alice-operator delegation-smoke

engineering-demo:
	uv run agntid-poc --agent-id service-operations-supervisor:v1 --user-id alice-operator engineering-demo

ops-chat:
	uv run agntid-poc --agent-id service-operations-supervisor:v1 --user-id alice-operator ops-chat
