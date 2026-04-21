"""MCPHandler — executes tools via an MCP (Model Context Protocol) server."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agent_tools.handlers.base import BaseHandler

if TYPE_CHECKING:
    from agent_tools.core.runtime import ExecutionContext


class MCPHandler(BaseHandler):
    """
    Calls a named tool on an MCP server.

    Requires the ``mcp`` extra: ``pip install "agent-tools[mcp]"``.
    """

    async def execute(self, ctx: "ExecutionContext") -> Any:
        try:
            from mcp import Client  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "The 'mcp' package is required for MCP tools. "
                "Install with: pip install 'agent-tools[mcp]'"
            ) from exc

        cfg = ctx.tool_def.config
        headers: dict[str, str] = {}
        from agent_tools.handlers.api_handler import _inject_auth_headers

        _inject_auth_headers(headers, ctx.resolved_auth)

        async with Client(cfg["endpoint"], headers=headers) as client:
            return await client.call_tool(cfg["tool_name"], ctx.validated_input)