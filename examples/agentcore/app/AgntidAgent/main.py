"""Amazon Bedrock AgentCore Runtime entrypoint for the AgntID example."""

from __future__ import annotations

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from starlette.responses import JSONResponse

from agntid_agentcore.errors import InvocationError
from agntid_agentcore.service import AgentCoreService

app = BedrockAgentCoreApp()
service = AgentCoreService.from_env()


@app.entrypoint
async def invoke(payload, context):
    """Validate one invocation and run it through the AgntID task boundary."""

    try:
        return await service.invoke(payload, context)
    except InvocationError as exc:
        app.logger.warning("Invocation rejected: %s", exc.public_message)
        return JSONResponse(
            {"error": exc.public_message},
            status_code=exc.status_code,
        )
    except Exception:
        # Do not echo MCP errors, headers, tokens, or model-provider details.
        app.logger.exception("Agent invocation failed")
        return JSONResponse(
            {"error": "The agent could not complete the request."},
            status_code=502,
        )


if __name__ == "__main__":
    app.run()
