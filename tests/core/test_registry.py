"""Unit tests for agent_tools.core.registry."""

from __future__ import annotations

import pytest
from agent_tools.core.definition import ExecutionConfig, ToolDefinition
from agent_tools.core.registry import ToolRegistry
from agent_tools.handlers.api_handler import APIHandler


def _make_defn(name: str) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        version="1.0",
        type="api",
        description=f"Tool {name}",
        config={},
        execution=ExecutionConfig(),
        handler_class=APIHandler,
    )


class TestToolRegistry:
    def test_register_and_get(self):
        reg = ToolRegistry()
        defn = _make_defn("alpha")
        reg.register(defn)
        assert reg.get("alpha") is defn

    def test_get_unknown_raises_key_error(self):
        reg = ToolRegistry()
        with pytest.raises(KeyError, match="'missing'"):
            reg.get("missing")

    def test_names_sorted(self):
        reg = ToolRegistry()
        for n in ["c_tool", "a_tool", "b_tool"]:
            reg.register(_make_defn(n))
        assert reg.names == ["a_tool", "b_tool", "c_tool"]

    def test_all_returns_in_name_order(self):
        reg = ToolRegistry()
        for n in ["z", "a", "m"]:
            reg.register(_make_defn(n))
        names = [d.name for d in reg.all()]
        assert names == ["a", "m", "z"]

    def test_overwrite_existing(self):
        reg = ToolRegistry()
        reg.register(_make_defn("dup"))
        reg.register(_make_defn("dup"))
        assert len(reg) == 1

    def test_contains(self):
        reg = ToolRegistry()
        reg.register(_make_defn("exists"))
        assert "exists" in reg
        assert "nope" not in reg

    def test_len(self):
        reg = ToolRegistry()
        assert len(reg) == 0
        reg.register(_make_defn("one"))
        assert len(reg) == 1
