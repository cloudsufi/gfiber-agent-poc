"""Tests for {{field}} / {{env:VAR}} templating in params and body."""
from __future__ import annotations

import httpx
import pytest
import respx

from agent_tools.core.definition import ExecutionConfig, ToolDefinition
from agent_tools.core.runtime import ExecutionContext
from agent_tools.handlers.api_handler import APIHandler


URL = "https://api.example.com/v1/resource"


def _ctx(
    *,
    params: dict | None = None,
    body_template: str | None = None,
    validated: dict | None = None,
    method: str = "GET",
) -> ExecutionContext:
    cfg = {
        "endpoint": URL,
        "method": method,
        "params": params or {},
        "auth": {},
        "timeout_seconds": 5,
    }
    if body_template is not None:
        cfg["body_template"] = body_template
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
    )


class TestParamsTemplating:
    @pytest.mark.asyncio
    @respx.mock
    async def test_field_token_substituted_in_params(self):
        route = respx.get(URL).mock(return_value=httpx.Response(200, json={}))
        ctx = _ctx(params={"city": "{{city}}"}, validated={"city": "London"})
        await APIHandler().execute(ctx)
        assert route.calls[0].request.url.params["city"] == "London"

    @pytest.mark.asyncio
    @respx.mock
    async def test_env_token_substituted_in_params(self, monkeypatch):
        monkeypatch.setenv("REGION_ID", "us-west-2")
        route = respx.get(URL).mock(return_value=httpx.Response(200, json={}))
        ctx = _ctx(params={"region": "{{env:REGION_ID}}"})
        await APIHandler().execute(ctx)
        assert route.calls[0].request.url.params["region"] == "us-west-2"

    @pytest.mark.asyncio
    @respx.mock
    async def test_literal_value_passthrough(self):
        route = respx.get(URL).mock(return_value=httpx.Response(200, json={}))
        ctx = _ctx(params={"fmt": "json"})
        await APIHandler().execute(ctx)
        assert route.calls[0].request.url.params["fmt"] == "json"


class TestBodyTemplating:
    @pytest.mark.asyncio
    @respx.mock
    async def test_body_template_field_substitution(self):
        route = respx.post(URL).mock(return_value=httpx.Response(200, json={}))
        ctx = _ctx(
            method="POST",
            body_template='{"id": "{{id}}", "action": "{{action}}"}',
            validated={"id": "ID-42", "action": "run"},
        )
        await APIHandler().execute(ctx)
        import json as j
        body = j.loads(route.calls[0].request.content.decode())
        assert body == {"id": "ID-42", "action": "run"}
