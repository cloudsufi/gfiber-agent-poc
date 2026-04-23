"""Unit tests for agent_tools.handlers.router."""

from __future__ import annotations

import pytest
from agent_tools.core.definition import ExecutionConfig, ToolDefinition
from agent_tools.core.tool_context import ToolContext
from agent_tools.core.runtime import ExecutionContext
from agent_tools.handlers.base import BaseHandler
from agent_tools.handlers.router import ExecutorRouter


class DummyHandler(BaseHandler):
    async def execute(self, ctx):
        return {"handler": "dummy"}


class TestExecutorRouter:
    def _make_ctx(self, handler_class=DummyHandler):
        defn = ToolDefinition(
            name="t",
            version="1.0",
            type="api",
            description="",
            config={},
            execution=ExecutionConfig(),
            handler_class=handler_class,
        )
        return ExecutionContext(
            tool_context=ToolContext(),
            tool_def=defn, raw_kwargs={})

    @pytest.mark.asyncio
    async def test_routes_to_handler(self):
        ctx = self._make_ctx()
        router = ExecutorRouter()

        async def terminal(c):
            pass

        result = await router.wrap(terminal)(ctx)
        assert result == {"handler": "dummy"}

    def test_caches_handler_instance(self):
        router = ExecutorRouter()

        h1 = router._get_handler(DummyHandler)
        h2 = router._get_handler(DummyHandler)
        assert h1 is h2

    @pytest.mark.asyncio
    async def test_sets_ctx_result(self):
        ctx = self._make_ctx()
        router = ExecutorRouter()

        async def terminal(c):
            pass

        await router.wrap(terminal)(ctx)
        assert ctx.result == {"handler": "dummy"}
