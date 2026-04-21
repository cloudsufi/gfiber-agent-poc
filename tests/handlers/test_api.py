"""Unit tests for agent_tools.handlers.api_handler."""
from __future__ import annotations

import pytest
import respx
import httpx

from agent_tools.core.definition import ExecutionConfig, ToolDefinition
from agent_tools.core.runtime import ExecutionContext
from agent_tools.handlers.api_handler import APIHandler, _inject_auth_headers


class TestInjectAuthHeaders:
    def test_bearer(self):
        h = {}
        _inject_auth_headers(h, {"type": "bearer", "token": "abc"})
        assert h["Authorization"] == "Bearer abc"

    def test_api_key(self):
        h = {}
        _inject_auth_headers(h, {"type": "api_key", "header": "X-Key", "value": "xyz"})
        assert h["X-Key"] == "xyz"

    def test_basic(self):
        h = {}
        _inject_auth_headers(h, {"type": "basic", "encoded": "dXNlcjpwYXNz"})
        assert h["Authorization"] == "Basic dXNlcjpwYXNz"

    def test_no_auth(self):
        h = {"Content-Type": "application/json"}
        _inject_auth_headers(h, {})
        assert "Authorization" not in h


class TestAPIHandler:
    def _make_ctx(self, url="https://api.example.com/v1/data", method="GET", params=None, auth=None):
        from agent_tools.handlers.api_handler import APIHandler
        defn = ToolDefinition(
            name="test",
            version="1.0",
            type="api",
            description="",
            config={
                "endpoint": url,
                "method": method,
                "params": params or {},
                "auth": {},
                "timeout_seconds": 5,
            },
            execution=ExecutionConfig(retries=0, timeout=5),
            handler_class=APIHandler,
        )
        ctx = ExecutionContext(
            tool_def=defn,
            raw_kwargs={},
            validated_input={},
            resolved_auth=auth or {},
        )
        return ctx

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_request(self):
        respx.get("https://api.example.com/v1/data").mock(
            return_value=httpx.Response(200, json={"value": 42})
        )
        ctx = self._make_ctx()
        result = await APIHandler().execute(ctx)
        assert result == {"value": 42}

    @pytest.mark.asyncio
    @respx.mock
    async def test_bearer_auth_header(self):
        route = respx.get("https://api.example.com/v1/data").mock(
            return_value=httpx.Response(200, json={})
        )
        ctx = self._make_ctx(auth={"type": "bearer", "token": "mytoken"})
        await APIHandler().execute(ctx)
        assert route.calls[0].request.headers["Authorization"] == "Bearer mytoken"

    @pytest.mark.asyncio
    @respx.mock
    async def test_http_error_raises(self):
        respx.get("https://api.example.com/v1/data").mock(
            return_value=httpx.Response(500)
        )
        ctx = self._make_ctx()
        with pytest.raises(httpx.HTTPStatusError):
            await APIHandler().execute(ctx)
