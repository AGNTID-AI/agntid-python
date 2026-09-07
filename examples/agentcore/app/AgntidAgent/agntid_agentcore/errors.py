"""Public-safe errors returned by the AgentCore entrypoint."""


class InvocationError(Exception):
    """An expected invocation failure with a safe client-facing message."""

    def __init__(self, status_code: int, public_message: str) -> None:
        super().__init__(public_message)
        self.status_code = status_code
        self.public_message = public_message
