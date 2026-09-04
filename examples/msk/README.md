# MSK (Microsoft Semantic Kernel) + AgntID

This example shows how to use the AgntID SDK with a Microsoft Semantic Kernel
Python ChatCompletionAgent so that every tool call goes through the AgntID MCP
proxy with per-prompt task attribution and policy enforcement.

## Quick start

```bash
pip install agntid-sdk[msk]
export OPENAI_API_KEY=your-openai-api-key
export AGNTID_MCP_URL=http://localhost:8082/mcp

python msk_demo.py                                        # default settings
python msk_demo.py --agent-name MyAgent --user-id user-42 # custom
python msk_demo.py --help
```

## Add AgntID to an existing MSK setup

If you already have an MSK ChatCompletionAgent that calls tools via MCP, you
need four insertion points. Everything else in your code stays the same.

### 1. Import the SDK

```python
import agntid
```

### 2. Connect to the AgntID MCP proxy and build the plugin

Replace your MCP client setup with:

```python
mcp_client = agntid.AgntidMCPClient(mcp_url)          # wraps fastmcp
async with mcp_client:
    tools_list = await agntid.get_tools_list(mcp_client)
    wrapped = agntid.wrap_client(mcp_client)           # task_id set per prompt via set_task_id()

    plugin = agntid.msk.create_plugin_from_mcp_tools(
        wrapped, tools_list,
        plugin_name="MCPTools",
    )
    kernel.add_plugin(plugin, plugin_name="MCPTools")
```

### 3. Wrap each user prompt in a task

Before invoking the agent for a user prompt, open a task.
`task_context` sends `task_close` automatically when the block exits.

```python
task_id = agntid.create_task(agent_id, user_id, user_prompt, sender=None)
async with agntid.task_context(mcp_client, task_id):
    ok, msg = await agntid.send_task_open_checked(
        mcp_client, task_id, agent_id, user_id, user_prompt,
    )
    if not ok:
        print(f"Task OPEN rejected: {msg}")
        continue
    wrapped.set_task_id(task_id)

    # ... invoke the agent as usual ...
```

### 4. (Optional) Check for policy denials

After the agent finishes, check whether any tool call was denied:

```python
denial = agntid.get_last_denial(clear=True)
if denial:
    print(agntid.format_denial(denial))
```

## Write a fresh MSK demo with AgntID

See `msk_demo.py` in this directory for a complete, runnable example.
The file is structured so the MSK setup and AgntID integration are
clearly separated with comments.

## What happens under the hood

1. `AgntidMCPClient` connects to the AgntID MCP proxy (wraps fastmcp).
2. `wrap_client` returns a client that injects `_task_id` into every tool call
   and strips `__agntid_*` fields from responses before the LLM sees them.
3. `create_plugin_from_mcp_tools` builds an MSK kernel plugin from the MCP
   tool list, handling name sanitization and `inputSchema` mapping.
4. Per prompt: `create_task` generates a task ID; `send_task_open_checked`
   registers it on the proxy; `task_context` closes it when done.
5. The proxy correlates each tool call to the prompt and enforces policy.
