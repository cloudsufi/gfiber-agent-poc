"""Unit tests for agent_tools.core.definition."""
from __future__ import annotations

from agent_tools.core.definition import ExecutionConfig, ToolDefinition, ToolTypeEntry
from agent_tools.core.settings import Settings


class TestExecutionConfig:
    def test_sentinel_resolved_with_settings(self):
        settings = Settings(default_retries=5, default_timeout=45)
        ec = ExecutionConfig(retries=-1, timeout=-1)
        resolved = ec.resolved(settings)
        assert resolved.retries == 5
        assert resolved.timeout == 45

    def test_explicit_values_not_overridden(self):
        settings = Settings(default_retries=5, default_timeout=45)
        ec = ExecutionConfig(retries=2, timeout=10)
        resolved = ec.resolved(settings)
        assert resolved.retries == 2
        assert resolved.timeout == 10

    def test_mixed_sentinels(self):
        settings = Settings(default_retries=3, default_timeout=30)
        ec = ExecutionConfig(retries=1, timeout=-1)
        resolved = ec.resolved(settings)
        assert resolved.retries == 1
        assert resolved.timeout == 30


class TestToolDefinition:
    def _make_defn(self, **kwargs):
        from agent_tools.handlers.api_handler import APIHandler
        defaults = dict(
            name="test_tool",
            version="1.0",
            type="api",
            description="desc",
            config={"endpoint": "https://x.com", "method": "GET"},
            execution=ExecutionConfig(),
            handler_class=APIHandler,
        )
        defaults.update(kwargs)
        return ToolDefinition(**defaults)

    def test_adk_schema_no_proto(self):
        defn = self._make_defn()
        schema = defn.adk_schema
        assert schema["name"] == "test_tool"
        assert schema["description"] == "desc"
        assert schema["parameters"] == {"type": "object", "properties": {}}

    def test_adk_schema_with_proto(self, sample_api_tool_dir):
        from agent_tools.proto.loader import ProtoLoader
        loader = ProtoLoader()
        proto = loader.load(sample_api_tool_dir / "request.proto")
        defn = self._make_defn(proto_input=proto)
        schema = defn.adk_schema
        assert "properties" in schema["parameters"]
        assert "id" in schema["parameters"]["properties"]


class TestToolTypeEntry:
    def test_fields(self, tmp_path):
        from pathlib import Path
        from agent_tools.handlers.api_handler import APIHandler
        entry = ToolTypeEntry(
            name="api",
            config_proto_path=tmp_path / "api.proto",
            handler_class=APIHandler,
        )
        assert entry.name == "api"
        assert entry.handler_class is APIHandler
