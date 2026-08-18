# agntid-sdk

Framework integrations share one canonical task and delegation contract. Install
only the framework extra you use (for example, `agntid-sdk[msk]`); the base SDK
and the LangChain Deep Agents adapter do not import a framework package.

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.2.0-orange)](CHANGELOG.md)

AgntID task-glue SDK for Python. Connects your AI agent to the AgntID MCP proxy so the platform can **correlate every tool call to the correct user prompt** and enforce **policy, audit, and guardrails** — with minimal code changes.

Works with any agent framework. First-class support for **Microsoft Semantic Kernel (MSK)** and **FastMCP**.

> **Status:** This SDK is currently in **alpha** and may evolve as the AgntID runtime stabilizes. We welcome feedback from early adopters.

<p align="center">
  <img src="https://github.com/AGNTID-AI/agntid-python/raw/main/docs/architecture-flow.svg" alt="Architecture: Agent Framework → AgntID Python SDK → AgntID Runtime → MCP Tool Servers" width="320"/>
</p>

**Architecture** — Your agent runs in your app and talks to the AgntID Python SDK; the SDK connects to the AgntID Runtime (MCP proxy + policy engine); the runtime forwards allowed tool calls to MCP tool servers.

---

## Installation

Requires **Python 3.10+**.

### Install from PyPI

```bash
pip install agntid-sdk
```

All dependencies (fastmcp, mcp, openai, semantic-kernel, rich, fastapi) are included.

### Install from release

Install a specific release wheel from GitHub:

```bash
pip install https://github.com/AGNTID-AI/agntid-python/releases/download/v0.1.1/agntid_sdk-0.1.1-py3-none-any.whl
```

Replace `v0.1.1` and the wheel filename with the [release](https://github.com/AGNTID-AI/agntid-python/releases) you want. The core SDK (with MCP transport) is included. For extras (e.g. MSK or OpenAI), install dependencies separately or use “Install from source” with extras.

### Install from source

Install the latest from the main branch:

```bash
pip install git+https://github.com/AGNTID-AI/agntid-python.git
```

With dev extras:

```bash
pip install -e ".[dev]"   # editable clone (see CONTRIBUTING.md)
```

### Editable install (development)

From a clone of this repo:

```bash
git clone https://github.com/AGNTID-AI/agntid-python.git
cd agntid-python
pip install -e ".[dev]"
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full development setup.

### Releases

Versioned releases with wheels are published on [GitHub Releases](https://github.com/AGNTID-AI/agntid-python/releases). For example:

| Release   | Wheel |
|-----------|--------|
| **v0.1.1** | `agntid_sdk-0.1.1-py3-none-any.whl` |

Install a specific version:

```bash
pip install https://github.com/AGNTID-AI/agntid-python/releases/download/v0.1.1/agntid_sdk-0.1.1-py3-none-any.whl
```

Or use **Install from source** / **Editable install** for the latest from `main`.

---

## Quick start

```python
import agntid

# 1. Connect to the AgntID MCP proxy
mcp_client = agntid.AgntidMCPClient("http://localhost:8082/mcp")

async with mcp_client:
    tools = await agntid.get_tools_list(mcp_client)
    wrapped = agntid.wrap_client(mcp_client)

    # 2. For each user prompt — open a task
    task_id = agntid.create_task(agent_id="my-agent", user_id="user-123", prompt=user_prompt)

    async with agntid.task_context(mcp_client, task_id):
        ok, msg = await agntid.send_task_open_checked(
            mcp_client, task_id, "my-agent", "user-123", user_prompt,
        )
        wrapped.set_task_id(task_id)

        # 3. Call tools through the wrapped client (task_id injected, __agntid_* stripped)
        result = await wrapped.call_tool_async("my_tool", {"arg": "value"})
    # task_close sent automatically when the block exits
```

---

## Framework examples

Each example has its own README with step-by-step integration instructions.

| Framework | Directory | Description |
|-----------|-----------|-------------|
| **LangChain Deep Agents** | [`examples/langchain-deepagents/`](examples/langchain-deepagents/) | Supervisor, specialist subagents, multi-turn context, HITL, and AgntID execution evidence |
| **MSK + OpenAI** | [`examples/msk/`](examples/msk/) | ChatCompletionAgent via Semantic Kernel with kernel plugin |
| **OpenAI + FastMCP** | [`examples/fastmcp/`](examples/fastmcp/) | OpenAI client with function-calling directly (no MSK) |

The compact MSK and FastMCP examples use this CLI interface:

```bash
python msk_demo.py --agent-name MyAgent --user-id user-42
python msk_demo.py --help
```

---

## API reference

### Core

| Function | Description |
|----------|-------------|
| `agntid.AgntidMCPClient(url)` | MCP client that wraps FastMCP (no direct `fastmcp` import needed) |
| `agntid.wrap_client(client, task_id=None)` | Returns a wrapper that injects `_task_id` and strips `__agntid_*` from responses; call `set_task_id(task_id)` before tool calls |
| `agntid.create_task(agent_id, user_id, prompt)` | Generates a task ID and registers task metadata |
| `agntid.close_task(task_id)` | Sends task close to the platform |
| `agntid.task_context(client, task_id)` | Async context manager — sends `task_close` on exit |
| `agntid.send_task_open_checked(...)` | Opens a task and returns `(ok, message)` |
| `agntid.get_tools_list(client)` | Lists tools from any MCP client |
| `agntid.get_last_denial(clear=True)` | Returns the last policy/task denial (if any) |
| `agntid.format_denial(denial)` | Formats a denial dict into a human-readable string |
| `agntid.print_result(result, tool_name=...)` | Rich-formatted result output |
| `agntid.print_denial(denial)` | Rich-formatted denial panel |
| `agntid.print_tools(tools, exclude=...)` | Rich-formatted tool list table |
| `agntid.print_connected(url, tool_count=...)` | Connection success banner |
| `agntid.print_error(msg)` | Error panel |
| `agntid.ToolResult` | Dict subclass; auto-renders with rich on `print()` |
| `agntid.DenialResult` | Denial wrapper; falsy; auto-renders with rich on `print()` |
| `agntid.require_env(*names)` | Checks required environment variables |
| `agntid.format_tools_display(tools, exclude)` | Formats tool list for display |
| `agntid.__version__` | SDK version string |

### MSK integration (`agntid.msk`)

| Function | Description |
|----------|-------------|
| `agntid.msk.create_plugin_from_mcp_tools(wrapped, tools, ...)` | Builds an MSK kernel plugin from MCP tools |
| `agntid.msk.agent_id_from_agent(agent)` | Derives agent ID from an MSK agent |

Included in the core SDK.

---

## Build

Build sdist and wheel (from the repo root):

```bash
make build
```

Artifacts are placed in `dist/`. The version is read from `pyproject.toml`.

Other targets:

```bash
make version      # print current version
make test         # run unit tests
make clean        # remove build artifacts
make install-dev  # install editable with dev extras
```

---

## Project structure

```
agntid-python/        # repo root
  src/agntid/
    __init__.py      # Public API + __version__
    client.py        # AgntidMCPClient, get_tools_list
    denial.py        # Denial parsing and formatting (framework-agnostic)
    display.py       # Rich-formatted output (ToolResult, DenialResult, print helpers)
    mcp_wrapper.py   # wrap_client — task_id injection, field stripping
    task.py          # Task lifecycle: create, open, close, context manager
    util.py          # require_env, format_tools_display
    msk.py           # Microsoft Semantic Kernel plugin builder
    _platform.py     # Wire format internals
    py.typed         # PEP 561 type marker
  examples/
    langchain-deepagents/ # Full multi-agent example with a three-step evaluator quick start
    msk/             # MSK + OpenAI demo (see examples/msk/README.md)
    fastmcp/         # FastMCP direct demo (see examples/fastmcp/README.md)
  tests/
    unit/
    integration/
  pyproject.toml     # Package metadata, deps, build config
  Makefile           # build, test, clean, install-dev targets
  LICENSE            # MIT
  CHANGELOG.md       # Release history
```

---

## Versioning

Semantic versioning (MAJOR.MINOR.PATCH). See [CHANGELOG.md](CHANGELOG.md) for release history.

## License

[MIT](LICENSE)
