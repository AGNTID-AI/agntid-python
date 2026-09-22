# Microsoft Semantic Kernel + AgntID

This runnable example gives a Semantic Kernel `ChatCompletionAgent` only the
MCP tools visible through AgntID. Every selected tool call carries the current
task ID and is checked by the runtime's profile and policies.

## 1. Prepare the shared runtime

Complete [the common runtime setup](../README.md) first. Continue only after
the direct model-free check can call `demo_add_numbers` and Reporting shows the
allowed event.

You need Python 3.10 or later. The interactive agent additionally needs an
OpenAI API key and a model available to that account.

## 2. Clone and install the MSK integration

From a new terminal:

```bash
git clone https://github.com/AGNTID-AI/agntid-python.git
cd agntid-python
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[msk,dev]"
```

PowerShell activation is:

```powershell
.venv\Scripts\Activate.ps1
```

If you already completed the shared setup in this checkout, reactivate its
`.venv` and run only the final installation command.

## 3. Configure the connection

For the local runtime started by the repository Compose file:

```bash
export AGNTID_MCP_URL=http://localhost:8082/mcp
```

When the runtime requires OAuth, also export the raw access token obtained by
your trusted application:

```bash
export AGNTID_ACCESS_TOKEN='<current OAuth access token>'
```

Do not include the `Bearer` prefix and never commit this value. Leave the
variable unset for an approved runtime that allows unauthenticated local
access.

## 4. Verify MSK without calling a model

From the repository root:

```bash
python examples/msk/msk_demo.py --check-runtime
```

Expected result:

```text
MSK readiness passed: demo_add_numbers is visible and the MCPTools plugin was built without calling a model.
```

This command connects to the real runtime, checks tool visibility, translates
the MCP schemas, and builds the Semantic Kernel plugin. It needs no model key.

Run the relevant SDK tests as an additional local check:

```bash
python -m pytest -q \
  tests/unit/test_msk.py \
  tests/unit/test_client.py \
  tests/unit/test_msk_demo.py
```

## 5. Run the interactive agent

Set the model configuration:

```bash
export OPENAI_API_KEY='<OpenAI API key>'
export OPENAI_CHAT_MODEL_ID=gpt-4o
```

Use a model available to your account, then start the example:

```bash
python examples/msk/msk_demo.py \
  --agent-name ArithmeticAssistant \
  --user-id user-42
```

At `Your prompt:`, enter:

```text
Add 11 and 22 using the available tool.
```

The wording of the response depends on the model, but it should report `33`.
Open AgntID Reporting and confirm an allowed `demo.add_numbers` event for the
same user, agent, task, and correlation ID. Type `n` at the continuation prompt
to exit.

`--user-id` is a demonstration input. A production service must derive the
user ID from its verified application session and the agent ID from trusted
deployment configuration; neither value may come from model output.

## Add AgntID to an existing Semantic Kernel agent

### Connect and build the plugin

```python
import os
import agntid

client = agntid.AgntidMCPClient(
    os.environ["AGNTID_MCP_URL"],
    access_token=os.getenv("AGNTID_ACCESS_TOKEN") or None,
)

async with client:
    runtime_tools = await agntid.get_tools_list(client)
    wrapped = agntid.wrap_client(client)
    plugin = agntid.msk.create_plugin_from_mcp_tools(
        wrapped,
        runtime_tools,
        plugin_name="MCPTools",
    )
    kernel.add_plugin(plugin, plugin_name="MCPTools")
```

The runtime already filtered `runtime_tools` using its protection profile,
tool state, and verified role grants. The SDK removes AgntID control tools,
sanitizes MCP names for Semantic Kernel, and maps model calls back to the
original MCP names. Runtime policy still evaluates the real arguments.

### Open one task for each user message

```python
task_id = agntid.create_task(agent_id, user_id, user_prompt)

async with agntid.task_context(client, task_id):
    ok, message = await agntid.send_task_open_checked(
        client,
        task_id,
        agent_id,
        user_id,
        user_prompt,
    )
    if not ok:
        raise RuntimeError(f"Task was not accepted: {message}")

    wrapped.set_task_id(task_id)
    async for response in agent.invoke(messages=user_prompt, thread=thread):
        print(response.content)
        thread = response.thread
```

A Semantic Kernel conversation thread may continue across turns, but every new
user message requires a new AgntID task. `task_context` closes the task even
when the model or tool call fails.

After the turn, surface any denial without trying to bypass it:

```python
if denial := agntid.get_last_denial(clear=True):
    print(agntid.format_denial(denial))
```

The complete implementation is [msk_demo.py](msk_demo.py).

## Troubleshooting

| Problem | Check |
| --- | --- |
| `No module named semantic_kernel` | Activate `.venv` and reinstall `-e ".[msk,dev]"` from the repository root. |
| Connection is refused | Confirm both Compose services are healthy and `AGNTID_MCP_URL` uses the published MCP port. |
| Authentication returns 401 | Export a current raw `AGNTID_ACCESS_TOKEN`; do not include `Bearer`. |
| Readiness reports a missing tool | Review `demo_add_numbers`, the runtime profile, synchronization state, and role grants. |
| The agent does not select the tool | Use the suggested arithmetic prompt and confirm `OPENAI_CHAT_MODEL_ID` supports tool calling. |
| A tool call is denied | Read the Reporting event and policy reason; do not retry with changed identity or hidden task arguments. |
| Reporting shows the wrong user | Replace the demo CLI value with identity from the application's verified session. |
