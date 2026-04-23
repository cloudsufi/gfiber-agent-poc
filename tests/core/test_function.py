"""Unit tests for agent_tools.core.function."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from agent_tools.core.definition import ExecutionConfig, ToolDefinition
from agent_tools.core.function import ToolFunction
from agent_tools.core.registry import ToolRegistry
from agent_tools.handlers.api_handler import APIHandler


def _make_runtime_with_tools(names):
    """Build a minimal runtime mock that has the given tool names."""
    from agent_tools.core.runtime import ToolRuntime

    registry = ToolRegistry()
    for name in names:
        defn = ToolDefinition(
            name=name,
            version="1.0",
            type="api",
            description=f"desc of {name}",
            config={},
            execution=ExecutionConfig(),
            handler_class=APIHandler,
        )
        registry.register(defn)

    rt = MagicMock(spec=ToolRuntime)
    rt._registry = registry
    rt.execute = AsyncMock(return_value={"ok": True})
    rt.all_tool_schemas = MagicMock(return_value=[{"name": n} for n in names])
    rt.tool_schemas_for = MagicMock(side_effect=lambda *ns: [{"name": n} for n in ns])
    return rt


class TestToolFunction:
    def test_name_attribute(self):
        rt = _make_runtime_with_tools(["alpha"])
        fn = ToolFunction("alpha", rt)
        assert fn.__name__ == "alpha"

    def test_repr(self):
        rt = _make_runtime_with_tools(["alpha"])
        fn = ToolFunction("alpha", rt)
        assert "alpha" in repr(fn)

    @pytest.mark.asyncio
    async def test_call_delegates_to_runtime(self):
        from agent_tools.core.tool_context import ToolContext

        rt = _make_runtime_with_tools(["alpha"])
        fn = ToolFunction("alpha", rt)
        tc = ToolContext()
        result = await fn(tc, x=1, y=2)
        # Check that execute was called with tool_context kwarg
        assert rt.execute.call_count == 1
        call_args = rt.execute.call_args
        assert call_args[0] == ("alpha", {"x": 1, "y": 2})
        assert call_args[1]["tool_context"] is tc
        assert result == {"ok": True}

    def test_schema_property(self):
        rt = _make_runtime_with_tools(["beta"])
        fn = ToolFunction("beta", rt)
        s = fn.schema
        assert s["name"] == "beta"

    def test_all_schemas(self):
        rt = _make_runtime_with_tools(["a", "b"])
        fn = ToolFunction("a", rt)
        schemas = fn.all_schemas()
        assert len(schemas) == 2

    def test_schemas_for(self):
        rt = _make_runtime_with_tools(["a", "b", "c"])
        fn = ToolFunction("a", rt)
        schemas = fn.schemas_for("a", "b")
        assert len(schemas) == 2

    def test_all_tools(self):
        rt = _make_runtime_with_tools(["x", "y"])
        fn = ToolFunction("x", rt)
        tools = fn.all_tools()
        assert len(tools) == 2
        assert all(isinstance(t, ToolFunction) for t in tools)

    def test_runtime_attribute_public(self):
        rt = _make_runtime_with_tools(["z"])
        fn = ToolFunction("z", rt)
        assert fn.runtime is rt

    def test_equality(self):
        rt = _make_runtime_with_tools(["a"])
        f1 = ToolFunction("a", rt)
        f2 = ToolFunction("a", rt)
        assert f1 == f2

    def test_hash(self):
        rt = _make_runtime_with_tools(["a"])
        fn = ToolFunction("a", rt)
        assert hash(fn) == hash("a")
