"""Dynamic header injection — env vars, request fields, runtime opt-in overrides."""

from __future__ import annotations

import httpx
import pytest
import respx
from agent_tools.core.context import with_request_headers
from agent_tools.core.tool_context import ToolContext
from agent_tools.core.definition import ExecutionConfig, ToolDefinition
from agent_tools.core.runtime import ExecutionContext
from agent_tools.handlers.api_handler import (
    APIHandler,
    _filter_runtime_headers,
    _render_headers,
)

URL = "https://api.example.com/v1/data"


def _ctx(
    headers: dict | None = None,
    validated: dict | None = None,
    auth: dict | None = None,
    runtime_headers: list[str] | None = None,
) -> ExecutionContext:
    cfg: dict = {
        "endpoint": URL,
        "method": "GET",
        "headers": headers or {},
        "params": {},
        "auth": {},
        "timeout_seconds": 5,
    }
    if runtime_headers is not None:
        cfg["runtime_headers"] = runtime_headers
    defn = ToolDefinition(
        name="test",
        version="1.0",
        type="api",
        description="",
        config=cfg,
        execution=ExecutionConfig(retries=0, timeout=5),
        handler_class=APIHandler,
    )
    return ExecutionContext(
        tool_def=defn,
        raw_kwargs=validated or {},
        validated_input=validated or {},
        resolved_auth=auth or {},
            tool_context=ToolContext(),
        )


class TestRenderHeaders:
    def test_literal_value_passthrough(self):
        assert _render_headers({"Accept": "application/json"}, {}) == {"Accept": "application/json"}

    def test_field_substitution(self):
        out = _render_headers({"X-Tenant": "{{tenant}}"}, {"tenant": "acme"})
        assert out == {"X-Tenant": "acme"}

    def test_env_substitution(self, monkeypatch):
        monkeypatch.setenv("APP_ID", "svc-42")
        out = _render_headers({"X-App-Id": "{{env:APP_ID}}"}, {})
        assert out == {"X-App-Id": "svc-42"}

    def test_missing_field_skips_header(self):
        out = _render_headers({"X-Tenant": "{{tenant}}", "Accept": "json"}, {})
        assert out == {"Accept": "json"}

    def test_missing_env_skips_header(self, monkeypatch):
        monkeypatch.delenv("NOT_SET", raising=False)
        out = _render_headers({"X-App-Id": "{{env:NOT_SET}}", "Accept": "json"}, {})
        assert out == {"Accept": "json"}

    def test_mixed_tokens_in_one_value(self, monkeypatch):
        monkeypatch.setenv("ENV_X", "env-val")
        out = _render_headers(
            {"X-Combo": "{{env:ENV_X}}:{{field}}"},
            {"field": "req-val"},
        )
        assert out == {"X-Combo": "env-val:req-val"}


class TestFilterRuntimeHeaders:
    def test_empty_allow_list_drops_all(self):
        assert _filter_runtime_headers({"X-Trace-Id": "v"}, []) == {}
        assert _filter_runtime_headers({"X-Trace-Id": "v"}, None) == {}

    def test_allow_listed_header_passes(self):
        assert _filter_runtime_headers({"X-Trace-Id": "v"}, ["X-Trace-Id"]) == {"X-Trace-Id": "v"}

    def test_comparison_is_case_insensitive(self):
        assert _filter_runtime_headers({"x-trace-id": "v"}, ["X-TRACE-ID"]) == {"x-trace-id": "v"}

    def test_non_allow_listed_dropped(self):
        assert _filter_runtime_headers(
            {"X-Trace-Id": "ok", "X-Secret": "nope"},
            ["X-Trace-Id"],
        ) == {"X-Trace-Id": "ok"}


class TestAPIHandlerHeaders:
    @pytest.mark.asyncio
    @respx.mock
    async def test_static_headers_sent(self):
        route = respx.get(URL).mock(return_value=httpx.Response(200, json={}))
        ctx = _ctx(headers={"X-Static": "yes"})
        await APIHandler().execute(ctx)
        assert route.calls[0].request.headers["X-Static"] == "yes"

    @pytest.mark.asyncio
    @respx.mock
    async def test_templated_header_from_request_field(self):
        route = respx.get(URL).mock(return_value=httpx.Response(200, json={}))
        ctx = _ctx(
            headers={"X-Tenant-Id": "{{tenant_id}}"},
            validated={"tenant_id": "acme-co"},
        )
        await APIHandler().execute(ctx)
        assert route.calls[0].request.headers["X-Tenant-Id"] == "acme-co"

    @pytest.mark.asyncio
    @respx.mock
    async def test_templated_header_from_env(self, monkeypatch):
        monkeypatch.setenv("APP_CONTEXT", "prod")
        route = respx.get(URL).mock(return_value=httpx.Response(200, json={}))
        ctx = _ctx(headers={"X-Context": "{{env:APP_CONTEXT}}"})
        await APIHandler().execute(ctx)
        assert route.calls[0].request.headers["X-Context"] == "prod"


class TestRuntimeHeaderGating:
    @pytest.mark.asyncio
    @respx.mock
    async def test_runtime_header_requires_opt_in(self):
        """Without runtime_headers in config, with_request_headers is ignored."""
        route = respx.get(URL).mock(return_value=httpx.Response(200, json={}))
        ctx = _ctx(headers={"X-Trace-Id": "static"})  # no runtime_headers declared
        with with_request_headers({"X-Trace-Id": "runtime-attempt"}):
            await APIHandler().execute(ctx)
        # static value wins — runtime attempt was dropped
        assert route.calls[0].request.headers["X-Trace-Id"] == "static"

    @pytest.mark.asyncio
    @respx.mock
    async def test_allow_listed_runtime_header_overrides_static(self):
        route = respx.get(URL).mock(return_value=httpx.Response(200, json={}))
        ctx = _ctx(
            headers={"X-Trace-Id": "static"},
            runtime_headers=["X-Trace-Id"],
        )
        with with_request_headers({"X-Trace-Id": "runtime-wins"}):
            await APIHandler().execute(ctx)
        assert route.calls[0].request.headers["X-Trace-Id"] == "runtime-wins"

    @pytest.mark.asyncio
    @respx.mock
    async def test_non_allow_listed_header_dropped(self):
        """A header the agent tried to inject but the tool didn't declare is ignored."""
        route = respx.get(URL).mock(return_value=httpx.Response(200, json={}))
        ctx = _ctx(runtime_headers=["X-Trace-Id"])
        with with_request_headers({"X-Trace-Id": "ok", "X-Secret": "should-not-leak"}):
            await APIHandler().execute(ctx)
        assert route.calls[0].request.headers.get("X-Trace-Id") == "ok"
        assert "x-secret" not in route.calls[0].request.headers

    @pytest.mark.asyncio
    @respx.mock
    async def test_allow_list_is_case_insensitive(self):
        route = respx.get(URL).mock(return_value=httpx.Response(200, json={}))
        ctx = _ctx(runtime_headers=["x-trace-id"])  # lower-case in yaml
        with with_request_headers({"X-Trace-Id": "cased"}):
            await APIHandler().execute(ctx)
        assert route.calls[0].request.headers["X-Trace-Id"] == "cased"

    @pytest.mark.asyncio
    @respx.mock
    async def test_auth_override_requires_authorization_in_allow_list(self):
        """Agent code can only override auth headers if the tool opts in."""
        route = respx.get(URL).mock(return_value=httpx.Response(200, json={}))

        # Without Authorization in allow-list → auth header stays as resolved.
        ctx = _ctx(auth={"type": "bearer", "token": "real-token"})
        with with_request_headers({"Authorization": "Bearer mock-token"}):
            await APIHandler().execute(ctx)
        assert route.calls[0].request.headers["Authorization"] == "Bearer real-token"

        # With Authorization in allow-list → runtime wins.
        ctx = _ctx(
            auth={"type": "bearer", "token": "real-token"},
            runtime_headers=["Authorization"],
        )
        with with_request_headers({"Authorization": "Bearer mock-token"}):
            await APIHandler().execute(ctx)
        assert route.calls[1].request.headers["Authorization"] == "Bearer mock-token"

    @pytest.mark.asyncio
    @respx.mock
    async def test_context_isolation_between_calls(self):
        route = respx.get(URL).mock(return_value=httpx.Response(200, json={}))

        with with_request_headers({"X-Scoped": "inside"}):
            await APIHandler().execute(_ctx(runtime_headers=["X-Scoped"]))
        await APIHandler().execute(_ctx(runtime_headers=["X-Scoped"]))

        assert route.calls[0].request.headers.get("X-Scoped") == "inside"
        assert "x-scoped" not in route.calls[1].request.headers
