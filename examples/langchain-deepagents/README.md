# LangChain Deep Agents with AgntID

This runnable example shows a supervisor built with LangChain Deep Agents using
AgntID-protected MCP tools. The supervisor plans work, delegates it to
least-privilege subagents, preserves multi-turn context, pauses sensitive
actions for human approval, and publishes the task, thread, delegation, tool,
policy, and audit evidence that AgntID uses.

The application source is copied unchanged from the proven
`agent-langchain` example at commit `f5cf84a`. This directory is a standalone
example project inside the Python SDK repository; its project metadata points
to the SDK checkout two directories above it.

## Evaluator quick start — three steps

Prerequisites: [`uv`](https://docs.astral.sh/uv/) and the runtime prepared by
[the common end-to-end setup](../README.md). Continue only after its direct
check can call `demo_add_numbers` and Reporting shows the allowed event. `uv`
installs Python 3.11 and all Python dependencies in an isolated environment
when required.

### 1. Get the example

```bash
git clone https://github.com/AGNTID-AI/agntid-python.git
cd agntid-python/examples/langchain-deepagents
```

If you already have the SDK checkout, only change into the example directory.

### 2. Configure the runtime

```bash
cp .env.example .env
```

Set `AGNTID_MCP_URL` in `.env` to the evaluator's MCP endpoint. The included
default targets the local AgntID development runtime. `OPENAI_API_KEY` is not
needed for the deterministic evaluation below; add it only for interactive
model-driven chat.

When the runtime requires OAuth, set the raw token obtained by your trusted
application. Do not include the `Bearer` prefix:

```dotenv
AGNTID_ACCESS_TOKEN=<current OAuth access token>
```

The bridge adds the authorization header only at the MCP transport boundary;
it does not place the token in graph state, prompts, memory, evidence files, or
tool arguments. Leave the value empty for an approved local runtime that allows
unauthenticated client access.

### 3. Run the safe evaluation

```bash
uv run --python 3.11 agntid-poc \
  --agent-id service-operations-supervisor:v1 \
  --user-id evaluator \
  delegation-smoke
```

There is no separate install or `uv sync` step: `uv run` installs this example,
its LangChain dependencies, and the enclosing AgntID SDK automatically.

Expected checkpoints include a `demo_add_numbers` tool call, an allowed policy
decision, a business result of `33`, and task/correlation identifiers. Confirm
the same allowed event in AgntID Reporting.

## What a successful evaluation proves

The safe evaluation uses a deterministic model and performs no notification,
scheduling, or payroll mutation. It should show:

- one compound prompt split between the incident and calculation specialists;
- a distinct trusted delegation identity and tool allowlist for each branch;
- AgntID intent and policy decisions for `demo_get_ticket` and
  `demo_add_numbers`;
- authoritative tool results plus task, correlation, and audit identifiers;
- a saved evidence file at `.demo_state/last_safe_delegation_run.json`.

Inspect the machine-readable transport evidence with:

```bash
jq '.transport_events' .demo_state/last_safe_delegation_run.json
```

## Optional interactive Deep Agent

Set `OPENAI_API_KEY` and, if needed, `MODEL` in `.env`, then run:

```bash
uv run --python 3.11 agntid-poc \
  --agent-id service-operations-supervisor:v1 \
  --user-id evaluator \
  ops-chat
```

Useful prompts, from simple to complex:

```text
Get the status and severity of LIVE-TKT-900. Do not send any notification.
```

```text
Get the status and severity of LIVE-TKT-900. Add 11 and 22 for responder capacity. Do not send notifications, schedule jobs, or export payroll records.
```

```text
Investigate LIVE-TKT-900. If and only if it is critical, notify #operations with the ticket ID, severity, and a short reason. Do not schedule jobs or export payroll records.
```

The interactive command keeps one checkpointed conversation thread until the
user types `exit`. AgntID creates one task per prompt and relates every tool and
subagent delegation back to that thread.

## Example structure

- `src/agntid_deepagents_poc/operations_agent.py` defines the supervisor,
  specialists, least-privilege tools, memory, and planning behavior.
- `src/agntid_deepagents_poc/bridge.py` manages AgntID task/delegation
  lifecycle and injects trusted correlation fields.
- `src/agntid_deepagents_poc/adapter.py` translates Deep Agents state into the
  framework-neutral AgntID execution contract.
- `src/agntid_deepagents_poc/operations_demo.py` contains the deterministic and
  interactive scenarios.
- `docs/architecture.md` explains boundaries and identity ownership.
- `docs/scenarios.md` lists the complete diagnostic command set.
- `tests/` verifies adapters, transport correlation, execution planning, and
  result parsing.

## Additional diagnostics

```bash
# Direct task-to-tool flow without a model
uv run --python 3.11 agntid-poc direct --first 11 --second 22

# Minimal LangChain plumbing with a deterministic model
uv run --python 3.11 agntid-poc framework-smoke --framework langchain

# Complete test suite
uv run --python 3.11 --extra dev pytest -q
```

The tests use fakes for model and MCP boundaries and do not require AWS,
OpenAI, an AgntID runtime, or an access token. The deterministic
`framework-smoke` and `delegation-smoke` commands do connect to the configured
AgntID runtime.

For the detailed design and broader experiment set, see
[architecture](docs/architecture.md), [scenarios](docs/scenarios.md), and the
[engineering demo](docs/engineering-demo.md).

## Troubleshooting

- Connection errors: verify `AGNTID_MCP_URL` and confirm the runtime MCP health
  endpoint is reachable from the evaluator's machine.
- OAuth 401 responses: provide a current raw `AGNTID_ACCESS_TOKEN` without the
  `Bearer` prefix and confirm it was issued for the AgntID protected resource.
- Missing `demo_*` tools: synchronize the runtime tool catalog and policies
  before running the example.
- Model authentication errors: `OPENAI_API_KEY` is required only by
  `ops-chat`, `langchain`, and `deepagents`; the safe evaluation does not use it.
- A denied tool call is not necessarily an example failure. Check the displayed
  AgntID policy reason and correlation ID; some diagnostic scenarios
  intentionally exercise denial paths.
- Never derive `--user-id`, `--agent-id`, delegation scope, or approval evidence
  from model output. Production services must load them from verified sessions
  and trusted deployment configuration.
