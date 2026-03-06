# OpenAI + FastMCP + AgntID

This example shows how to use the AgntID SDK with the **OpenAI Python client
directly** (no MSK / Semantic Kernel). It connects to the AgntID MCP proxy,
converts MCP tools into OpenAI function-calling definitions, and runs a
standard chat-completion loop with per-prompt task attribution and policy
enforcement.

Same pattern as the MSK example but with fewer dependencies — just
`openai` and `agntid-sdk`.

## Quick start

```bash
pip install agntid-sdk openai
export OPENAI_API_KEY=your-openai-api-key
export AGNTID_MCP_URL=http://localhost:8082/mcp

python openai_demo.py                                        # default settings
python openai_demo.py --agent-name MyAgent --user-id user-42 # custom
python openai_demo.py --help
```

## Add AgntID to an existing OpenAI function-calling setup

If you already have an OpenAI client that calls tools, the integration
requires four changes. Everything else stays the same.

### 1. Import the SDK

```python
import agntid
```

### 2. Replace your MCP client and build OpenAI tool defs

```python
mcp_client = agntid.AgntidMCPClient(mcp_url)

async with mcp_client:
    tools_list = await agntid.get_tools_list(mcp_client)
    wrapped = agntid.wrap_client(mcp_client)

    # Convert MCP tools to OpenAI function definitions
    openai_tools = [...]  # see openai_demo.py for the conversion helper
```

### 3. Wrap each user prompt in a task

```python
task_id = agntid.create_task(agent_id, user_id, user_prompt)
async with agntid.task_context(mcp_client, task_id):
    ok, msg = await agntid.send_task_open_checked(
        mcp_client, task_id, agent_id, user_id, user_prompt,
    )
    if not ok:
        print(f"Task OPEN rejected: {msg}")
        continue
    wrapped.set_task_id(task_id)

    # ... run your chat completion loop, calling tools via wrapped ...
```

### 4. Execute tool calls through the wrapped client

In your tool-call handler, use the wrapped client instead of calling
tools directly:

```python
result = await wrapped.call_tool_async(tool_name, arguments)
```

### 5. (Optional) Check for policy denials

```python
denial = agntid.get_last_denial(clear=True)
if denial:
    print(agntid.format_denial(denial))
```

## What happens under the hood

1. `AgntidMCPClient` connects to the AgntID MCP proxy (wraps fastmcp
   internally so your code has no direct fastmcp dependency).
2. MCP tools are converted to OpenAI function-calling format (name
   sanitization, parameter schema mapping).
3. `wrap_client` injects `_task_id` into every tool call and strips
   `__agntid_*` fields from responses before the LLM sees them.
4. `create_task` + `send_task_open_checked` register the intent on the proxy.
5. `task_context` sends `task_close` automatically when the block exits.
6. The proxy correlates each tool call to the prompt and enforces policy.
