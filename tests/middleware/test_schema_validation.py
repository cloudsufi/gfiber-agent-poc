"""Unit tests for agent_tools.middleware.schema_validation."""

from __future__ import annotations

import pytest
from agent_tools.core.runtime import ExecutionContext
from agent_tools.core.tool_context import ToolContext
from agent_tools.middleware.schema_validation import SchemaValidationMiddleware


@pytest.fixture()
def input_schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["name"],
        "properties": {"name": {"type": "string"}},
    }


@pytest.fixture()
def output_schema() -> dict:
    return {
        "type": "object",
        "properties": {"result": {"type": "string"}},
    }


class TestSchemaValidationMiddleware:
    @pytest.mark.asyncio
    async def test_validates_input(self, mock_tool_definition, input_schema):
        mock_tool_definition.input_schema = input_schema
        ctx = ExecutionContext(
            tool_def=mock_tool_definition,
            raw_kwargs={"name": "alice"},
            tool_context=ToolContext(),
        )

        async def handler(c):
            assert c.validated_input == {"name": "alice"}
            return {}

        mw = SchemaValidationMiddleware()
        await mw.wrap(handler)(ctx)

    @pytest.mark.asyncio
    async def test_input_unknown_field_raises(self, mock_tool_definition, input_schema):
        mock_tool_definition.input_schema = input_schema
        ctx = ExecutionContext(
            tool_def=mock_tool_definition,
            raw_kwargs={"name": "alice", "extra": 1},
            tool_context=ToolContext(),
        )

        async def handler(c):
            return {}

        mw = SchemaValidationMiddleware()
        with pytest.raises(ValueError, match="invalid input"):
            await mw.wrap(handler)(ctx)

    @pytest.mark.asyncio
    async def test_input_missing_required_raises(self, mock_tool_definition, input_schema):
        mock_tool_definition.input_schema = input_schema
        ctx = ExecutionContext(
            tool_context=ToolContext(),
            tool_def=mock_tool_definition, raw_kwargs={})

        async def handler(c):
            return {}

        mw = SchemaValidationMiddleware()
        with pytest.raises(ValueError, match="invalid input"):
            await mw.wrap(handler)(ctx)

    @pytest.mark.asyncio
    async def test_validates_output(self, mock_tool_definition, output_schema):
        mock_tool_definition.output_schema = output_schema
        ctx = ExecutionContext(
            tool_context=ToolContext(),
            tool_def=mock_tool_definition, raw_kwargs={})

        async def handler(c):
            return {"result": "done"}

        mw = SchemaValidationMiddleware()
        result = await mw.wrap(handler)(ctx)
        assert result == {"result": "done"}

    @pytest.mark.asyncio
    async def test_output_drops_unknown_fields(self, mock_tool_definition, output_schema):
        mock_tool_definition.output_schema = output_schema
        ctx = ExecutionContext(
            tool_context=ToolContext(),
            tool_def=mock_tool_definition, raw_kwargs={})

        async def handler(c):
            return {"result": "done", "extra_from_api": 42}

        mw = SchemaValidationMiddleware()
        result = await mw.wrap(handler)(ctx)
        assert result == {"result": "done"}

    @pytest.mark.asyncio
    async def test_no_schema_passes_through(self, mock_tool_definition):
        ctx = ExecutionContext(
            tool_def=mock_tool_definition,
            raw_kwargs={"any": "data"},
            tool_context=ToolContext(),
        )

        async def handler(c):
            assert c.validated_input == {"any": "data"}
            return {"raw": True}

        mw = SchemaValidationMiddleware()
        result = await mw.wrap(handler)(ctx)
        assert result == {"raw": True}
