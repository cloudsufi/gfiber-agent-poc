"""Unit tests for agent_tools.core.runtime."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from agent_tools.core.definition import ExecutionConfig, ToolDefinition
from agent_tools.core.registry import ToolRegistry
from agent_tools.core.runtime import ExecutionContext, ToolRuntime
from agent_tools.core.settings import Settings
from agent_tools.handlers.api_handler import APIHandler


def _make_registry(*names):
    reg = ToolRegistry()
    for n in names:
        reg.register(ToolDefinition(
            name=n, version="1.0", type="api", description=f"d{n}",
            config={}, execution=ExecutionConfig(), handler_class=APIHandler,
        ))
    return reg


class TestExecutionContext:
    def test_defaults(self):
        defn = ToolDefinition(
            name="t", version="1.0", type="api", description="",
            config={}, execution=ExecutionConfig(), handler_class=APIHandler,
        )
        ctx = ExecutionContext(tool_def=defn, raw_kwargs={"a": 1})
        assert ctx.validated_input == {}
        assert ctx.resolved_auth == {}
        assert ctx.proto_input is None
        assert ctx.result is None


class TestToolRuntime:
    def _make_runtime(self, *names):
        reg = _make_registry(*names)
        settings = Settings(default_retries=0, default_timeout=5)
        with patch("agent_tools.middleware.pipeline.MiddlewarePipeline.build") as mock_build:
            mock_pipeline = MagicMock()
            mock_pipeline.run = AsyncMock(return_value={"mocked": True})
            mock_build.return_value = mock_pipeline
            rt = ToolRuntime(registry=reg, settings=settings)
        return rt

    @pytest.mark.asyncio
    async def test_execute_calls_pipeline(self):
        rt = self._make_runtime("tool_a")
        result = await rt.execute("tool_a", {"key": "val"})
        assert result == {"mocked": True}

    def test_execute_unknown_tool_raises(self):
        rt = self._make_runtime("tool_a")
        with pytest.raises(KeyError):
            import asyncio
            asyncio.get_event_loop().run_until_complete(
                rt.execute("nonexistent", {})
            )

    def test_tool_schemas_for(self):
        rt = self._make_runtime("a", "b")
        schemas = rt.tool_schemas_for("a")
        assert len(schemas) == 1
        assert schemas[0]["name"] == "a"

    def test_all_tool_schemas(self):
        rt = self._make_runtime("a", "b", "c")
        schemas = rt.all_tool_schemas()
        assert len(schemas) == 3
