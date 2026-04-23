"""Unit tests for the CTA (Dialogflow CX) handler."""

from __future__ import annotations

import pytest
from agent_tools.core.definition import ExecutionConfig, ToolDefinition
from agent_tools.core.tool_context import ToolContext
from agent_tools.core.runtime import ExecutionContext
from agent_tools.handlers.cta_handler import CTAHandler


def _ctx(cfg: dict, validated: dict | None = None) -> ExecutionContext:
    defn = ToolDefinition(
        name="test_cta",
        version="1.0",
        type="cta",
        description="",
        config=cfg,
        execution=ExecutionConfig(retries=0, timeout=5),
        handler_class=CTAHandler,
    )
    return ExecutionContext(
        tool_def=defn,
        raw_kwargs=validated or {},
        validated_input=validated or {},
            tool_context=ToolContext(),
        )


class TestCTAHandlerMockMode:
    @pytest.mark.asyncio
    async def test_mock_returns_deterministic_response(self):
        ctx = _ctx(
            cfg={
                "project_id": "p",
                "location": "us-central1",
                "agent_id": "a",
                "language_code": "en",
                "mock_mode": True,
                "session_id_field": "session_id",
            },
            validated={"text": "Hello", "session_id": "sid-1"},
        )
        result = await CTAHandler().execute(ctx)
        assert result["session_id"] == "sid-1"
        assert result["agent_response"].endswith("You said: Hello")
        assert result["intent"] == "mock.echo"
        assert result["language_code"] == "en"

    @pytest.mark.asyncio
    async def test_mock_generates_session_when_field_missing(self):
        ctx = _ctx(
            cfg={"project_id": "p", "location": "us", "agent_id": "a", "mock_mode": True},
            validated={"text": "Hi"},
        )
        result = await CTAHandler().execute(ctx)
        assert result["session_id"]  # non-empty
        assert len(result["session_id"]) >= 16  # uuid4 hex

    @pytest.mark.asyncio
    async def test_empty_text_raises(self):
        ctx = _ctx(
            cfg={"mock_mode": True, "project_id": "p", "location": "us", "agent_id": "a"},
            validated={"text": ""},
        )
        with pytest.raises(ValueError, match="no text found"):
            await CTAHandler().execute(ctx)

    @pytest.mark.asyncio
    async def test_custom_text_field_is_honored(self):
        ctx = _ctx(
            cfg={
                "project_id": "p",
                "location": "us",
                "agent_id": "a",
                "mock_mode": True,
                "text_field": "utterance",
            },
            validated={"utterance": "Hi via custom field"},
        )
        result = await CTAHandler().execute(ctx)
        assert "Hi via custom field" in result["agent_response"]


class TestCTAFallbackWithoutSDK:
    @pytest.mark.asyncio
    async def test_missing_dialogflow_sdk_returns_mock(self, monkeypatch):
        """When mock_mode=False but the SDK isn't installed, the handler still runs."""
        import builtins

        real_import = builtins.__import__

        def block_cx(name, *a, **kw):
            if name.startswith("google.cloud.dialogflowcx"):
                raise ImportError("forced")
            return real_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", block_cx)

        ctx = _ctx(
            cfg={
                "project_id": "p",
                "location": "us",
                "agent_id": "a",
                "mock_mode": False,  # real path requested
            },
            validated={"text": "Hi", "session_id": "s"},
        )
        result = await CTAHandler().execute(ctx)
        assert result["intent"] == "mock.echo"
