# Changelog

All notable changes to the `agntid-sdk` package are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
