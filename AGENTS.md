# Coding-agent integration contract

Use the public `agntid` package; do not copy wire-format internals from the
runtime. The smallest safe integration follows these rules:

1. Load `agent_id` and `user_id` from trusted application state, never model output.
2. Create one AgntID task for every new user prompt and always close it.
3. Call `send_task_open_details`, then `filter_tools_for_task`, before giving tools
   to a model. Treat `IntentPreparationError` as a stopped run; do not silently
   expose the broader profile-visible list.
4. Execute business tools only through `wrap_client` so task and delegation IDs
   are application-controlled and runtime metadata is removed from model input.
5. Never expose AgntID task, delegation, or action control tools to the model.
6. Put OAuth tokens only on the MCP transport. Never place them in prompts, tool
   arguments, graph state, memory, source files, or logs.
7. Runtime policy is authoritative. A framework allowlist or intent shortlist can
   narrow tools but cannot authorize a call or reveal a runtime-hidden tool.

Start with `examples/direct/intent_shortlist.py`. Framework examples live under
`examples/`; the OpenAI example in `examples/fastmcp/` demonstrates binding the
task-specific shortlist before the first model call.

Run these deterministic checks after SDK changes:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -q -p no:cacheprovider tests/unit
PYTHONDONTWRITEBYTECODE=1 examples/langchain-deepagents/.venv/bin/pytest \
  -q -p no:cacheprovider examples/langchain-deepagents/tests
```
