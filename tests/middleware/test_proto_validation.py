"""Unit tests for agent_tools.middleware.proto_validation."""
from __future__ import annotations

import pytest

from agent_tools.core.runtime import ExecutionContext
from agent_tools.middleware.proto_validation import ProtoValidationMiddleware
from agent_tools.proto.loader import ProtoLoader


@pytest.fixture()
def req_descriptor(tmp_path):
    p = tmp_path / "req.proto"
    p.write_text('syntax = "proto3";\nmessage Req { string name = 1; }\n')
    return ProtoLoader().load(p)


@pytest.fixture()
def resp_descriptor(tmp_path):
    p = tmp_path / "resp.proto"
    p.write_text('syntax = "proto3";\nmessage Resp { string result = 1; }\n')
    return ProtoLoader().load(p)


class TestProtoValidationMiddleware:
    @pytest.mark.asyncio
    async def test_validates_input(self, mock_tool_definition, req_descriptor):
        mock_tool_definition.proto_input = req_descriptor
        ctx = ExecutionContext(
            tool_def=mock_tool_definition,
            raw_kwargs={"name": "alice"},
        )

        async def handler(c):
            assert c.validated_input == {"name": "alice"}
            return {}

        mw = ProtoValidationMiddleware()
        await mw.wrap(handler)(ctx)

    @pytest.mark.asyncio
    async def test_validates_output(self, mock_tool_definition, resp_descriptor):
        mock_tool_definition.proto_output = resp_descriptor
        ctx = ExecutionContext(tool_def=mock_tool_definition, raw_kwargs={})

        async def handler(c):
            return {"result": "done"}

        mw = ProtoValidationMiddleware()
        result = await mw.wrap(handler)(ctx)
        assert result == {"result": "done"}

    @pytest.mark.asyncio
    async def test_no_proto_passes_through(self, mock_tool_definition):
        ctx = ExecutionContext(
            tool_def=mock_tool_definition,
            raw_kwargs={"any": "data"},
        )

        async def handler(c):
            assert c.validated_input == {"any": "data"}
            return {"raw": True}

        mw = ProtoValidationMiddleware()
        result = await mw.wrap(handler)(ctx)
        assert result == {"raw": True}
