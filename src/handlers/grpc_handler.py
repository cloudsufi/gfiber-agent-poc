"""GRPCHandler — executes tools via a gRPC service."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agent_tools.handlers.base import BaseHandler

if TYPE_CHECKING:
    from agent_tools.core.runtime import ExecutionContext


class GRPCHandler(BaseHandler):
    """
    Calls a gRPC method on a remote service.

    The config must include ``_stub_class`` (injected by the caller or test)
    pointing to the generated gRPC stub class, because it cannot be derived
    from YAML alone without code generation.
    """

    async def execute(self, ctx: "ExecutionContext") -> Any:
        import grpc  # type: ignore[import]

        cfg = ctx.tool_def.config
        auth = ctx.resolved_auth

        if cfg.get("use_tls"):
            ssl_creds = grpc.ssl_channel_credentials()
            if auth.get("type") == "bearer":
                call_creds = grpc.access_token_call_credentials(auth["token"])
                credentials = grpc.composite_channel_credentials(ssl_creds, call_creds)
            else:
                credentials = ssl_creds
            channel = grpc.aio.secure_channel(cfg["endpoint"], credentials)
        else:
            channel = grpc.aio.insecure_channel(cfg["endpoint"])

        stub_class = cfg.get("_stub_class")
        if stub_class is None:
            raise ValueError(
                f"Tool '{ctx.tool_def.name}': '_stub_class' must be set in config for gRPC tools."
            )

        stub = stub_class(channel)
        method = getattr(stub, cfg["method_name"])
        resp = await method(ctx.proto_input)

        if ctx.tool_def.proto_output:
            return ctx.tool_def.proto_output.to_dict(resp)
        return {"response": str(resp)}