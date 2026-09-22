# Run the framework examples end to end

Use this page once before choosing Microsoft Semantic Kernel, LangChain/Deep
Agents, or Amazon Bedrock AgentCore. It takes a new checkout from runtime
startup to a verified protected tool call. Each framework README starts from
the same known-good runtime state.

## What you need

- an AgntID portal account with container-registry access;
- Docker 20.10+ with Docker Compose v2;
- Python 3.11 recommended for all examples (MSK supports 3.10; `uv` can install
  Python for the LangChain and AgentCore projects);
- approximately 4 GB RAM and 5 GB free disk space;
- outbound HTTPS access to the AgntID registry, control plane, and the model
  provider used by your chosen framework.

The first runtime start downloads an approximately 900 MB intent model and can
take several minutes.

## 1. Clone the source-of-truth checkout

```bash
git clone https://github.com/AGNTID-AI/agntid-python.git
cd agntid-python
```

All commands below identify their working directory. Do not copy an individual
example away from the repository because the LangChain and AgentCore projects
package the SDK from this checkout.

## 2. Register and start an AgntID runtime

In the AgntID portal:

1. Open **Runtimes** and select **Add Runtime**.
2. Name the runtime, generate its one-time bootstrap token, and copy the token
   immediately.
3. Do not put the bootstrap token in a shell command, source file, screenshot,
   ticket, or log.

From the `agntid-python` repository root, sign in and start runtime 2.0.0:

```bash
docker login registry.agntid.ai
docker compose up -d
docker compose ps
```

For staging or another AgntID instance, set its domain for both registry login
and startup:

```bash
export DOMAIN=staging.agntid.ai
docker login "registry.${DOMAIN}"
docker compose up -d
```

Wait until `achr-runtime` and `achr-intent-parser` are healthy, then verify the
runtime API:

```bash
curl --fail http://localhost:8080/health
```

Open <http://localhost:8080>, enter the bootstrap token, and select **Connect
to Control Plane**. In the portal, open the runtime's **Setup** tab, review the
**Medium / READ_WRITE** protection profile, and wait for **5 of 5** checks plus
**Runtime sync: Applied**. The built-in `demo_add_numbers` tool should now be
visible.

The framework processes connect to:

```bash
export AGNTID_MCP_URL=http://localhost:8082/mcp
```

If you changed `MCP_PORT` when starting Compose, use that public port instead.

## 3. Verify one protected call without a model

Create a local SDK environment from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python examples/direct/direct_tool_call.py
```

PowerShell activation is `.venv\Scripts\Activate.ps1`; the remaining commands
are the same.

Expected checkpoints are:

```text
Connected to runtime
Discovered ... tools
Tool call successful: demo_add_numbers
```

The final result contains the sum of `11` and `22`. In the portal, open
**Reporting** and confirm an allowed `demo.add_numbers` event with the matching
task and correlation information. Do not continue to a framework until this
direct check passes.

## 4. Connect when the runtime requires OAuth

The bootstrap token only registers a runtime. It is not an MCP access token.
When **Runtime Security** requires OAuth, your trusted application must obtain
a current access token for the AgntID protected resource through its configured
OAuth flow. Export only the raw access token:

```bash
export AGNTID_ACCESS_TOKEN='<current OAuth access token>'
```

Do not include the `Bearer` prefix; the examples add it at the transport
boundary. Never commit the token, put it in a prompt, or store it in browser
code. The MSK, direct, and LangChain examples read this variable. AgentCore
forwards the same token through its dedicated custom authorization header, as
described in its README.

Portal administrators can follow the hosted
[OAuth configuration guide](https://docs.agntid.ai/mcp/oauth/) to create and
validate the client credential, require OAuth, and review verified role grants.

For an approved local-only test, open the runtime's **Security** tab and select
**Allow Unauthenticated Access**. Re-enable OAuth before normal use.

## 5. Choose and verify a framework

| Framework | Model-free readiness command | Complete guide |
| --- | --- | --- |
| Microsoft Semantic Kernel | `python -m pip install -e ".[msk]" && python examples/msk/msk_demo.py --check-runtime` | [MSK](msk/README.md) |
| LangChain | `uv run --project examples/langchain-deepagents --python 3.11 agntid-poc framework-smoke --framework langchain` | [LangChain and Deep Agents](langchain-deepagents/README.md) |
| Deep Agents | `uv run --project examples/langchain-deepagents --python 3.11 agntid-poc framework-smoke --framework deepagents` | [LangChain and Deep Agents](langchain-deepagents/README.md) |
| Amazon Bedrock AgentCore | `make -C examples/agentcore test` | [AgentCore](agentcore/README.md) |

The readiness commands do not call a model provider. The two framework-smoke
commands do call the local AgntID runtime and therefore exercise its current
profile and policies. AgentCore's test target uses an in-memory MCP double;
continue with its direct-smoke section for a real local runtime call.

## Runtime troubleshooting

| Symptom | Check |
| --- | --- |
| Compose service is unhealthy | Run `docker compose logs -f`; the intent model may still be downloading. |
| Bootstrap token is rejected | Generate a fresh token for the same portal instance and enter it only in the local runtime UI. |
| MCP connection fails | Confirm Compose is healthy and `AGNTID_MCP_URL` uses the published MCP port. |
| `demo_add_numbers` is absent | Review the runtime profile, tool classification, individual state, runtime sync, and OAuth role grants. |
| A call is denied | Read the Reporting event and policy reason; do not retry with altered identity or hidden arguments. |
| OAuth returns 401 | Confirm the token is current, issued for the AgntID protected resource, and exported without the `Bearer` prefix. |

Stop the runtime without deleting its stored configuration:

```bash
docker compose down
```

Do not use `docker compose down -v` unless you intentionally want to delete the
runtime registration, configuration, local database, logs, and model cache.
