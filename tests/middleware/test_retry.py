"""Unit tests for agent_tools.middleware.retry."""
from __future__ import annotations

import pytest

from agent_tools.core.definition import ExecutionConfig
from agent_tools.core.runtime import ExecutionContext
from agent_tools.core.settings import Settings
from agent_tools.middleware.retry import RetryMiddleware


class TestRetryMiddleware:
    @pytest.mark.asyncio
    async def test_success_first_attempt(self, mock_tool_definition):
        settings = Settings(default_retries=2, default_timeout=30)
        mock_tool_definition.execution = ExecutionConfig(retries=1, timeout=5)
        ctx = ExecutionContext(tool_def=mock_tool_definition, raw_kwargs={})
        calls = []

        async def handler(c):
            calls.append(1)
            return {"ok": True}

        mw = RetryMiddleware(settings)
        result = await mw.wrap(handler)(ctx)
        assert result == {"ok": True}
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_retries_on_failure(self, mock_tool_definition):
        settings = Settings(default_retries=3, default_timeout=30)
        mock_tool_definition.execution = ExecutionConfig(retries=2, timeout=5)
        ctx = ExecutionContext(tool_def=mock_tool_definition, raw_kwargs={})
        calls = []

        async def flaky(c):
            calls.append(1)
            if len(calls) < 3:
                raise ConnectionError("network error")
            return {"ok": True}

        mw = RetryMiddleware(settings)
        # Patch asyncio.sleep to avoid delay in tests
        import asyncio
        from unittest.mock import patch, AsyncMock
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await mw.wrap(flaky)(ctx)
        assert result == {"ok": True}
        assert len(calls) == 3

    @pytest.mark.asyncio
    async def test_raises_after_exhausting_retries(self, mock_tool_definition):
        settings = Settings(default_retries=3, default_timeout=30)
        mock_tool_definition.execution = ExecutionConfig(retries=1, timeout=5)
        ctx = ExecutionContext(tool_def=mock_tool_definition, raw_kwargs={})

        async def always_fails(c):
            raise ValueError("always bad")

        mw = RetryMiddleware(settings)
        from unittest.mock import patch, AsyncMock
        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(ValueError, match="always bad"):
                await mw.wrap(always_fails)(ctx)
