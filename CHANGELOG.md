# Changelog

All notable changes to the `agntid-sdk` package are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - Unreleased

### Added
- Framework-neutral execution, plan, delegation, action, and approval context.
- LangChain and Deep Agents adapter plus a locked, runnable example project.
- Delegation and action lifecycle helpers.

### Changed
- Framework dependencies are optional again; use `[msk]` or `[openai]` as needed.
- The Semantic Kernel plugin excludes all AgntID runtime control tools by default.
- The direct smoke example uses `demo_add_numbers(first_number, second_number)`.

## [0.1.1] - 2026-03-09

### Added
- Rich-formatted display module (`display.py`) with `ToolResult`, `ToolResultScalar`, `DenialResult`.
- `print(result)` auto-renders with rich colours for tool results and denials.
- New display functions: `print_result`, `print_denial`, `print_tools`, `print_connected`, `print_task_opened`, `print_error`.
- `rich` as an explicit core dependency.

### Changed
- All dependencies (fastapi, fastmcp, mcp, openai, semantic-kernel, rich) are now core — no optional extras needed.
- `call_tool_async` returns `DenialResult` on policy denial instead of raising `ToolError`.
- `strip_platform_fields` handles `CallToolResult` objects and extracts `__agntid_result`.

### Fixed
- Empty `dependencies = []` caused `pip install` to skip all dependencies.

## [0.1.0] - 2026-02-11

### Added
- `create_task` / `close_task` — register and close tasks on the AgntID MCP proxy.
- `wrap_client` — MCP client wrapper that injects `_task_id` and strips `__agntid_*` response fields.
- `AgntidMCPClient` — drop-in MCP client that wraps FastMCP (no direct `fastmcp` import needed).
- `task_context` — async context manager for automatic `task_close`.
- `send_task_open_checked` — task open with result validation.
- `get_last_denial` / `format_denial` — policy denial capture and human-readable formatting.
- `require_env` / `format_tools_display` — utility helpers.
- `agntid.msk` — Microsoft Semantic Kernel plugin builder (`create_plugin_from_mcp_tools`).
- Examples: `examples/msk/msk_demo.py` (MSK + OpenAI) and `examples/fastmcp/openai_demo.py` (OpenAI direct, no MSK).
- Build support: `make sdk-build` produces sdist + wheel; wired into root `make build`.
