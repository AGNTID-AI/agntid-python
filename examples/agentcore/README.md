# Amazon Bedrock AgentCore + LangGraph + AgntID

This complete example hosts a LangGraph agent with Amazon Bedrock AgentCore
Runtime and sends every MCP operation through AgntID. AgentCore supplies the
hosting contract and model loop; AgntID remains the enforcement boundary for
tool visibility, task correlation, policy, credentials, and audit evidence.

The example follows the current AgentCore CLI project layout. It does **not**
use the retired `bedrock-agentcore-starter-toolkit` workflow.

## What is included

- an AgentCore HTTP entrypoint at `app/AgntidAgent/main.py`;
- a LangGraph ReAct agent using a Bedrock model;
- conversion of profile-visible AgntID MCP tools into LangChain tools;
- one AgntID task open/close lifecycle per AgentCore invocation;
- trusted user identity and OAuth bearer forwarding through dedicated
  AgentCore custom headers;
- an AgentCore request-header allowlist for those two custom headers;
- an operator-owned tool allowlist that can only reduce the runtime-visible
  tools;
- deterministic unit and HTTP contract tests that need neither AWS credentials
  nor an AWS account;
- a disabled-by-default direct smoke mode for exercising a local AgntID
  runtime without an LLM.

## Request path

```text
trusted application/backend
  -> AgentCore Runtime /invocations
     custom user-id + AgntID bearer headers
  -> LangGraph agent
  -> AgntID MCP runtime
     task open -> checked tool call -> task close
  -> MCP server
```

The AgntID access token is an end-user OAuth token for the AgntID protected
resource. It is not an AgentCore workload access token and must not be put in
the JSON payload, environment, logs, or model context.

## Prerequisites

- Python 3.11 or 3.12
- [`uv`](https://docs.astral.sh/uv/)
- Node.js 20 or later
- the current AgentCore CLI:

```bash
npm install --global @aws/agentcore
agentcore --version
```

This checkout was verified with AgentCore CLI `0.28.1` and
`bedrock-agentcore==1.22.0`.

Prepare the example once after cloning. This builds an ignored wheel from the
current `agntid-python` checkout so the same SDK code is available both locally
and inside the deployment ZIP:

```bash
cd examples/agentcore
make setup
```

## Test locally without AWS

From the `agntid-python` repository root:

```bash
cd examples/agentcore
make test
make validate
```

The tests use an in-memory MCP double and a deterministic agent runner. They
verify the AgentCore `/invocations` contract, custom-header propagation, bearer
validation, user identity, allowlist intersection, hidden task arguments,
task open/tool/task close ordering, correlation injection, result cleanup, and
the no-model direct smoke path. They do not contact AWS, Bedrock, AgntID, or a
model provider.

## Run a deterministic local runtime smoke

This optional smoke uses AgentCore locally and calls `demo_add_numbers` through
your local AgntID runtime. It does not call Bedrock or another model. Start the
local AgntID runtime first and make sure the tool is visible under its current
protection profile.

Copy the local settings:

```bash
cp agentcore/.env.local.example agentcore/.env.local
```

Edit `agentcore/.env.local` and set:

```dotenv
AGNTID_MCP_URL=http://localhost:8082/mcp
AGNTID_TOOL_ALLOWLIST=demo_add_numbers
AGNTID_ENABLE_DIRECT_SMOKE=true
```

Keep `AGNTID_REQUIRE_BEARER=true` for an OAuth-protected MCP address. For a
local runtime that intentionally has no client authentication, set it to
`false` only in `.env.local`.

Start AgentCore local development in terminal 1:

```bash
make dev
```

Invoke it from terminal 2. Identity is always required; do not replace an
unknown user with a shared default.

```bash
export AGNTID_USER_ID=user-42

curl --fail-with-body --silent --show-error \
  --request POST http://localhost:8080/invocations \
  --header 'Content-Type: application/json' \
  --header 'X-Amzn-Bedrock-AgentCore-Runtime-Session-Id: 123e4567-e89b-12d3-a456-426614174000' \
  --header "X-Amzn-Bedrock-AgentCore-Runtime-Custom-Agntid-User-Id: ${AGNTID_USER_ID}" \
  --data '{
    "prompt": "Add 11 and 22",
    "direct_tool": {
      "name": "demo_add_numbers",
      "arguments": {"first_number": 11, "second_number": 22}
    }
  }'
```

For an OAuth-protected MCP address, also export the token and add the header.
The shell history records only the variable name, not the token value:

```bash
export AGNTID_ACCESS_TOKEN='<current OAuth access token>'
```

```text
--header "X-Amzn-Bedrock-AgentCore-Runtime-Custom-Agntid-Authorization: Bearer ${AGNTID_ACCESS_TOKEN}"
```

A successful response includes `mode: "direct-smoke"`, `result`, `task_id`, and
`visible_tool_count`. Use `task_id` to find the matching AgntID reporting
record. Turn direct smoke mode off after the check.

## Run the LangGraph agent locally

Set `AGNTID_ENABLE_DIRECT_SMOKE=false`. Configure AWS credentials with Bedrock
model access, restart `make dev`, keep the same
identity and bearer headers, and send only a prompt:

```bash
curl --fail-with-body --silent --show-error \
  --request POST http://localhost:8080/invocations \
  --header 'Content-Type: application/json' \
  --header 'X-Amzn-Bedrock-AgentCore-Runtime-Session-Id: 123e4567-e89b-12d3-a456-426614174000' \
  --header "X-Amzn-Bedrock-AgentCore-Runtime-Custom-Agntid-User-Id: ${AGNTID_USER_ID}" \
  --header "X-Amzn-Bedrock-AgentCore-Runtime-Custom-Agntid-Authorization: Bearer ${AGNTID_ACCESS_TOKEN}" \
  --data '{"prompt":"Add 11 and 22 using the available tool."}'
```

The model sees only the allowlisted intersection of the tools returned by
AgntID. It never sees the bearer token or the internal task correlation
argument.

## Deploy to AgentCore Runtime

Deployment creates AWS resources and requires AWS credentials. Before running
it, replace the local MCP URL in `agentcore/agentcore.json` with an HTTPS AgntID
runtime address reachable from AgentCore. Do not deploy a `localhost` URL.

Add your account and a supported region to `agentcore/aws-targets.json`:

```json
[
  {
    "name": "dev",
    "description": "AgntID AgentCore development target",
    "account": "123456789012",
    "region": "us-east-1"
  }
]
```

Validate and inspect the CodeZip package before deployment:

```bash
make validate
make package
make deploy
```

The generated SDK wheel under `app/AgntidAgent/vendor/` is ignored by Git. The
Make targets rebuild it when the SDK source changes and ensure the deployment
ZIP contains the real `agntid` package rather than a checkout-only editable
path. Run them from a complete repository checkout, not from a copied
`examples/agentcore` directory.

Invoke the deployed runtime with a stable session ID and the two AgntID custom
headers:

```bash
agentcore invoke \
  --runtime AgntidAgent \
  --target dev \
  --session-id 123e4567-e89b-12d3-a456-426614174000 \
  --header "X-Amzn-Bedrock-AgentCore-Runtime-Custom-Agntid-User-Id: ${AGNTID_USER_ID}" \
  --header "X-Amzn-Bedrock-AgentCore-Runtime-Custom-Agntid-Authorization: Bearer ${AGNTID_ACCESS_TOKEN}" \
  'Add 11 and 22 using the available tool.'
```

## OAuth handoff requirements

The browser must not invoke this runtime with a stored refresh token. A trusted
backend should:

1. complete Authorization Code with PKCE against the AgntID protected resource;
2. store access and refresh tokens server-side;
3. refresh the access token before invoking AgentCore;
4. derive the stable AgntID user ID from trusted session or verified token data;
5. pass the access token and user ID in the dedicated custom headers;
6. redact those headers from application, proxy, trace, and error logs.

The example consumes that secure handoff; it does not implement a browser login
or token store. AgentCore invocation authentication (AWS IAM or a configured
runtime authorizer) remains separate from AgntID MCP authorization.

## Security invariants

- `AGNTID_MCP_URL`, agent identity, model, and allowlist are operator settings,
  never payload fields.
- The custom user ID is required. Missing identity stays missing and fails
  closed.
- The application allowlist cannot reveal a tool hidden by AgntID.
- AgntID checks the actual arguments again on every tool call.
- Control tools are never exposed to the model.
- Direct smoke mode is disabled by default and remains constrained by the same
  runtime-visible list, operator allowlist, task lifecycle, and policy checks.
- Task close runs even when the model or tool call fails.
- Raw bearer tokens are never returned or deliberately logged.

## Troubleshooting

- `Missing required header`: pass the exact custom user ID and authorization
  header names shown above. Header matching is case-insensitive.
- `No allowlisted AgntID tools are visible`: compare `AGNTID_TOOL_ALLOWLIST`
  with the runtime's current profile-filtered MCP tool list.
- local connection failure: confirm `AGNTID_MCP_URL` and that the runtime is
  ready before starting AgentCore.
- deployed connection failure: the MCP URL must be reachable from AgentCore's
  configured network mode and use a trusted TLS certificate.
- Bedrock model error: confirm model access, execution-role permissions,
  region support, and `AGNTID_MODEL_ID`.
- old `agentcore configure` or `agentcore launch` instructions: uninstall the
  old starter toolkit and use the current `@aws/agentcore` CLI commands shown
  here.
