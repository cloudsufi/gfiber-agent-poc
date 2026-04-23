"""
MCPHandler — executes tools via an MCP (Model Context Protocol) server.

MCP is an open protocol for exposing tools, prompts, and resources to LLM
clients. This handler acts as an MCP **client**, forwarding the validated
request to a named tool on a remote MCP server and returning whatever the
server replies with.

Modes
-----
* ``mock_mode: true`` — no network, no SDK. Returns a deterministic stub
  of the form ``{"tool_name": ..., "endpoint": ..., "echo": <inputs>,
  "mock": true}``. Useful for demos, tests, and local development before
  an MCP server is deployed.
* ``mock_mode: false`` (default) — opens an MCP client to
  ``config["endpoint"]``, forwards any auth-resolved headers, and calls
  ``call_tool(config["tool_name"], ctx.validated_input)``.

The ``mcp`` package is an optional install — it's only imported when a
real call is attempted, so mock-mode MCP tools work even without it
installed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agent_tools.handlers.base import BaseHandler

if TYPE_CHECKING:
    from agent_tools.core.runtime import ExecutionContext


class MCPHandler(BaseHandler):
    """
    Calls a named tool on an MCP server.

    With ``mock_mode: true`` in the tool config the handler returns a
    deterministic stub instead of opening an MCP client — useful for demos
    and tests without a running MCP server. Otherwise requires the ``mcp``
    extra: ``pip install "ai-agent-shared-tools[mcp]"``.
    """

    async def execute(self, ctx: ExecutionContext) -> Any:
        cfg = ctx.tool_def.config

        if cfg.get("mock_mode"):
            return {
                "tool_name": cfg.get("tool_name", ""),
                "endpoint": cfg.get("endpoint", ""),
                "echo": dict(ctx.validated_input),
                "mock": True,
            }

        try:
            from mcp import Client  # type: ignore[attr-defined]
        except ImportError as exc:
            raise ImportError(
                "The 'mcp' package is required for MCP tools. "
                "Install with: pip install 'ai-agent-shared-tools[mcp]'"
            ) from exc

        headers: dict[str, str] = {}
        from agent_tools.handlers.api_handler import _inject_auth_headers

        _inject_auth_headers(headers, ctx.resolved_auth)

        async with Client(cfg["endpoint"], headers=headers) as client:
            return await client.call_tool(cfg["tool_name"], ctx.validated_input)
