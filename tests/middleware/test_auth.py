"""Unit tests for agent_tools.middleware.auth."""
from __future__ import annotations

import os
import base64

import pytest

from agent_tools.middleware.auth import resolve_auth


class TestResolveAuth:
    def test_empty_returns_empty(self):
        assert resolve_auth({}) == {}

    def test_bearer(self, monkeypatch):
        monkeypatch.setenv("MY_TOKEN", "secret123")
        result = resolve_auth({"bearer": {"token_env": "MY_TOKEN"}})
        assert result == {"type": "bearer", "token": "secret123"}

    def test_bearer_missing_env_returns_empty_string(self, monkeypatch):
        monkeypatch.delenv("MISSING_VAR", raising=False)
        result = resolve_auth({"bearer": {"token_env": "MISSING_VAR"}})
        assert result["token"] == ""

    def test_api_key(self, monkeypatch):
        monkeypatch.setenv("MY_KEY", "key-abc")
        result = resolve_auth({"api_key": {"header_name": "X-Api-Key", "key_env": "MY_KEY"}})
        assert result == {"type": "api_key", "header": "X-Api-Key", "value": "key-abc"}

    def test_basic(self, monkeypatch):
        monkeypatch.setenv("U", "alice")
        monkeypatch.setenv("P", "password")
        result = resolve_auth({"basic": {"username_env": "U", "password_env": "P"}})
        expected = base64.b64encode(b"alice:password").decode()
        assert result == {"type": "basic", "encoded": expected}


class TestAuthMiddleware:
    @pytest.mark.asyncio
    async def test_injects_resolved_auth(self, mock_tool_definition, monkeypatch):
        from agent_tools.core.runtime import ExecutionContext
        from agent_tools.middleware.auth import AuthMiddleware

        monkeypatch.setenv("TEST_API_KEY", "tok-xyz")
        mock_tool_definition.config["auth"] = {"bearer": {"token_env": "TEST_API_KEY"}}

        ctx = ExecutionContext(tool_def=mock_tool_definition, raw_kwargs={})
        results = []

        async def capture(c):
            results.append(c.resolved_auth)
            return {}

        mw = AuthMiddleware()
        await mw.wrap(capture)(ctx)
        assert results[0] == {"type": "bearer", "token": "tok-xyz"}
