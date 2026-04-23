"""Unit tests for MCPHandler mock_mode path."""

from __future__ import annotations

import pytest
from agent_tools.core.definition import ExecutionConfig, ToolDefinition
from agent_tools.core.tool_context import ToolContext
from agent_tools.core.runtime import ExecutionContext
from agent_tools.handlers.mcp_handler import MCPHandler


def _ctx(cfg: dict, validated: dict | None = None) -> ExecutionContext:
    defn = ToolDefinition(
        name="test_mcp",
        version="1.0",
        type="mcp",
        description="",
        config=cfg,
        execution=ExecutionConfig(retries=0, timeout=5),
        handler_class=MCPHandler,
    )
    return ExecutionContext(
        tool_def=defn,
        raw_kwargs=validated or {},
        validated_input=validated or {},
            tool_context=ToolContext(),
        )


class TestMCPHandlerMockMode:
    @pytest.mark.asyncio
    async def test_mock_echoes_input(self):
        ctx = _ctx(
            cfg={
                "endpoint": "https://example.com/mcp",
                "tool_name": "search_docs",
                "mock_mode": True,
            },
            validated={"query": "billing policy", "top_k": 2},
        )
        result = await MCPHandler().execute(ctx)
        assert result == {
            "tool_name": "search_docs",
            "endpoint": "https://example.com/mcp",
            "echo": {"query": "billing policy", "top_k": 2},
            "mock": True,
        }

    @pytest.mark.asyncio
    async def test_real_mode_without_mcp_raises(self, monkeypatch):
        """Without the mcp package installed and mock_mode=False, we surface a clear error."""
        import builtins

        real_import = builtins.__import__

        def block_mcp(name, *a, **kw):
            if name == "mcp":
                raise ImportError("forced")
            return real_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", block_mcp)

        ctx = _ctx(
            cfg={
                "endpoint": "https://example.com/mcp",
                "tool_name": "search_docs",
                "mock_mode": False,
            },
            validated={"query": "x"},
        )
        with pytest.raises(ImportError, match="mcp.*required"):
            await MCPHandler().execute(ctx)
