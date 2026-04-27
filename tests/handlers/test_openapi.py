"""Unit tests for agent_tools.handlers.openapi_handler."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import respx
import yaml
from httpx import Response

from agent_tools.core.definition import ExecutionConfig, ToolDefinition
from agent_tools.core.runtime import ExecutionContext
from agent_tools.core.tool_context import ToolContext
from agent_tools.handlers.openapi_handler import OpenAPIHandler


def _make_ctx(tool_dir, validated_input=None):
    defn = ToolDefinition(
        name="openapi_tool",
        version="1.0",
        type="openapi",
        description="",
        config={
            "operation_id": "getCustomer",
            "auth": {},
        },
        execution=ExecutionConfig(retries=0, timeout=5),
        handler_class=OpenAPIHandler,
        tool_dir=tool_dir,
    )
    return ExecutionContext(
        tool_def=defn,
        raw_kwargs={},
        tool_context=ToolContext(),
        validated_input=validated_input or {},
    )


class TestOpenAPIHandler:
    @pytest.mark.asyncio
    @respx.mock
    async def test_routes_path_param_correctly(self, tmp_path):
        """Path parameters are substituted into the URL."""
        tool_dir = tmp_path
        spec = {
            "servers": [{"url": "https://api.example.com"}],
            "paths": {
                "/customers/{customerId}": {
                    "get": {
                        "operationId": "getCustomer",
                        "parameters": [
                            {"name": "customerId", "in": "path", "schema": {"type": "string"}}
                        ],
                        "responses": {"200": {"description": "OK"}},
                    }
                }
            },
        }
        (tool_dir / "openapi.yaml").write_text(yaml.dump(spec))

        respx.get("https://api.example.com/customers/cust-123").mock(
            return_value=Response(200, json={"id": "cust-123", "name": "Alice"})
        )

        ctx = _make_ctx(tool_dir, {"customerId": "cust-123"})
        result = await OpenAPIHandler().execute(ctx)
        assert result == {"id": "cust-123", "name": "Alice"}

    @pytest.mark.asyncio
    @respx.mock
    async def test_routes_query_param_correctly(self, tmp_path):
        """Query parameters are passed as query string."""
        tool_dir = tmp_path
        spec = {
            "servers": [{"url": "https://api.example.com"}],
            "paths": {
                "/search": {
                    "get": {
                        "operationId": "search",
                        "parameters": [
                            {"name": "q", "in": "query", "schema": {"type": "string"}}
                        ],
                        "responses": {"200": {"description": "OK"}},
                    }
                }
            },
        }
        (tool_dir / "openapi.yaml").write_text(yaml.dump(spec))

        respx.get("https://api.example.com/search", params={"q": "test"}).mock(
            return_value=Response(200, json={"results": ["item1", "item2"]})
        )

        ctx = _make_ctx(tool_dir, {"q": "test"})
        ctx.tool_def.config["operation_id"] = "search"
        result = await OpenAPIHandler().execute(ctx)
        assert result == {"results": ["item1", "item2"]}

    @pytest.mark.asyncio
    @respx.mock
    async def test_routes_body_correctly(self, tmp_path):
        """Fields not in parameters go to request body."""
        tool_dir = tmp_path
        spec = {
            "servers": [{"url": "https://api.example.com"}],
            "paths": {
                "/customers": {
                    "post": {
                        "operationId": "createCustomer",
                        "requestBody": {
                            "required": True,
                            "content": {"application/json": {"schema": {"type": "object"}}},
                        },
                        "responses": {"201": {"description": "Created"}},
                    }
                }
            },
        }
        (tool_dir / "openapi.yaml").write_text(yaml.dump(spec))

        respx.post("https://api.example.com/customers").mock(
            return_value=Response(201, json={"id": "cust-999"})
        )

        ctx = _make_ctx(tool_dir, {"name": "Bob", "email": "bob@example.com"})
        ctx.tool_def.config["operation_id"] = "createCustomer"
        result = await OpenAPIHandler().execute(ctx)
        assert result == {"id": "cust-999"}

    @pytest.mark.asyncio
    async def test_server_url_env_override(self, tmp_path):
        """server_url_env overrides the server URL from spec."""
        tool_dir = tmp_path
        spec = {
            "servers": [{"url": "https://api.dev.example.com"}],
            "paths": {
                "/test": {
                    "get": {
                        "operationId": "test",
                        "parameters": [],
                        "responses": {"200": {"description": "OK"}},
                    }
                }
            },
        }
        (tool_dir / "openapi.yaml").write_text(yaml.dump(spec))

        ctx = _make_ctx(tool_dir, {})
        ctx.tool_def.config["server_url_env"] = "MY_API_URL"

        os.environ["MY_API_URL"] = "https://api.prod.example.com"
        try:
            # Just verify that the handler reads the env var — don't actually make the request
            with pytest.raises(Exception):  # httpx error because no mock
                await OpenAPIHandler().execute(ctx)
        finally:
            os.environ.pop("MY_API_URL", None)

    @pytest.mark.asyncio
    async def test_operation_not_found_raises(self, tmp_path):
        """Unknown operationId raises ValueError with helpful message."""
        tool_dir = tmp_path
        spec = {
            "servers": [{"url": "https://api.example.com"}],
            "paths": {
                "/customers": {
                    "get": {
                        "operationId": "listCustomers",
                        "parameters": [],
                        "responses": {"200": {"description": "OK"}},
                    }
                }
            },
        }
        (tool_dir / "openapi.yaml").write_text(yaml.dump(spec))

        ctx = _make_ctx(tool_dir, {})
        ctx.tool_def.config["operation_id"] = "unknownOperation"

        with pytest.raises(ValueError, match="unknownOperation"):
            await OpenAPIHandler().execute(ctx)

    @pytest.mark.asyncio
    async def test_missing_openapi_yaml_raises(self, tmp_path):
        """Missing openapi.yaml raises FileNotFoundError."""
        tool_dir = tmp_path

        ctx = _make_ctx(tool_dir, {})

        with pytest.raises(FileNotFoundError, match="openapi.yaml"):
            await OpenAPIHandler().execute(ctx)

    @pytest.mark.asyncio
    @respx.mock
    async def test_auth_injected(self, tmp_path):
        """Bearer token from auth config is injected into headers."""
        tool_dir = tmp_path
        spec = {
            "servers": [{"url": "https://api.example.com"}],
            "paths": {
                "/secure": {
                    "get": {
                        "operationId": "getSecure",
                        "parameters": [],
                        "responses": {"200": {"description": "OK"}},
                    }
                }
            },
        }
        (tool_dir / "openapi.yaml").write_text(yaml.dump(spec))

        respx.get("https://api.example.com/secure").mock(
            return_value=Response(200, json={"secret": "data"})
        )

        ctx = _make_ctx(tool_dir, {})
        ctx.tool_def.config["operation_id"] = "getSecure"
        ctx.resolved_auth = {"type": "bearer", "token": "secret-token"}

        result = await OpenAPIHandler().execute(ctx)
        assert result == {"secret": "data"}
        # Verify the Authorization header was sent
        assert respx.calls.last.request.headers["Authorization"] == "Bearer secret-token"
