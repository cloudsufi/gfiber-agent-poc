"""Unit tests for agent_tools.core.type_registry."""
from __future__ import annotations

from pathlib import Path

import pytest

from agent_tools.core.definition import ToolTypeEntry
from agent_tools.core.type_registry import ToolTypeRegistry, default_type_registry
from agent_tools.handlers.api_handler import APIHandler


class TestToolTypeRegistry:
    def test_register_and_get(self, tmp_path):
        reg = ToolTypeRegistry()
        reg.register("custom", tmp_path / "c.proto", APIHandler)
        entry = reg.get("custom")
        assert entry.name == "custom"
        assert entry.handler_class is APIHandler

    def test_get_unknown_raises(self):
        reg = ToolTypeRegistry()
        with pytest.raises(KeyError, match="Unknown tool type"):
            reg.get("nonexistent")

    def test_known_types_sorted(self):
        reg = ToolTypeRegistry()
        reg.register("z", Path("/tmp/z.proto"), APIHandler)
        reg.register("a", Path("/tmp/a.proto"), APIHandler)
        assert reg.known_types() == ["a", "z"]

    def test_contains(self):
        reg = ToolTypeRegistry()
        reg.register("mine", Path("/tmp/x.proto"), APIHandler)
        assert "mine" in reg
        assert "other" not in reg

    def test_default_registry_has_builtin_types(self):
        for expected in ("api", "mcp", "python", "grpc", "bigquery", "rest"):
            assert expected in default_type_registry
