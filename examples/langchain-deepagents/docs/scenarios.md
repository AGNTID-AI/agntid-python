# POC scenarios

## 1. Protocol and policy proof without an LLM

This isolates AgntID from model behavior and proves the exact task lifecycle.

```bash
make direct-allow
make direct-deny
```

The current local policy allows `11 + 22` and denies `11 + 32` because
`second_number` must be in the configured `20..30` range. The denial output
includes the policy name, failed constraint, task, agent, user, runtime, and
policy snapshot when supplied by the runtime.

## 2. Same agent acting for two users

```bash
make identity
```

Both executions use the same stable agent ID but distinct users and task IDs.
This shows the actor model needed for questions such as "which agent acted?"
and "on whose behalf?" without treating the user and agent as one principal.

## 3. Framework plumbing without a model API key

```bash
make langchain-smoke
make deepagents-smoke
```

A deterministic fake chat model emits a real LangChain tool call. Everything
after that model decision is real: graph execution, MCP adapter, task-ID
interceptor, local AgntID policy pipeline, demo backend, and audit envelope.
This is suitable for regression tests and demos where an external model is not
available.

## 4. Safe compound prompt and child delegation

```bash
make delegation-smoke
```

This deterministic prompt asks for a ticket lookup and an addition while
explicitly prohibiting notifications, scheduling, payroll export, and all other
actions. It must produce two successful business calls with two delegation IDs.
The command exits non-zero if either MCP call is denied or errors, even when the
scripted agent would otherwise continue to a final answer.

Inspect the exact canonical transport:

```bash
jq '.transport_events' .demo_state/last_safe_delegation_run.json
```

## 5. Multi-turn conversation with a real model

```bash
cp .env.example .env
# Set OPENAI_API_KEY and MODEL
make ops-chat
```

Try these in the same chat to exercise accumulated context:

```text
Get the status and severity of LIVE-TKT-900. Do not send any notification.
Using that ticket as context, add 11 and 22 for responder capacity. Keep the no-notification restriction active.
What prior request and active restriction are you using for this turn?
```

The LangGraph thread retains the conversation. The adapter also sends a bounded
summary of prior user prompts plus explicit negative constraints; it does not
send raw chain-of-thought.

## 6. Normal model-driven single-tool agents

Set a provider key and model, then pass a natural-language prompt:

```bash
cp .env.example .env
# Edit OPENAI_API_KEY in .env

uv run agntid-poc \
  --agent-id arithmetic-assistant:v1 \
  --user-id oidc-subject-123 \
  langchain "Please add 11 and 22"

uv run agntid-poc \
  --agent-id operations-deep-agent:v1 \
  --user-id oidc-subject-123 \
  deepagents "Please add 11 and 22"
```

The CLI accepts IDs to make the flow visible. A service must replace those CLI
values with identities resolved before the prompt reaches the model.

## Useful next POCs

- Policy by user role: same agent and arguments, two users with different roles.
- Agent-version policy: allow `arithmetic-agent:v1`, deny an unregistered agent.
- Human-in-the-loop verification: bind transported approval evidence to an
  authenticated approver and signed/authoritative decision record.
- Credential brokerage: use an AWS S3 tool and confirm scoped, short-lived
  credentials never enter model context.
- Additional framework adapters: implement the same neutral contract for a
  second orchestration framework without changing AgntID core policy code.
- Multi-tenant isolation: same user-shaped ID in two organizations must resolve
  to different principals and policy namespaces.
- Replay/expiry: close a task and verify a later call with that task ID is
  denied.
- Policy snapshot reproducibility: retain the snapshot ID used for every tool
  decision and explain later why it was allowed or denied.
