"""Unit tests for agent_tools.core.loader."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from agent_tools.core.loader import ToolLoader
from agent_tools.core.definition import ToolDefinition


class TestToolLoader:
    def test_load_missing_yaml_raises(self, tmp_path):
        loader = ToolLoader()
        with pytest.raises(FileNotFoundError):
            loader.load(tmp_path / "no_tool")

    def test_load_invalid_yaml_raises(self, tmp_path):
        tool_dir = tmp_path / "bad"
        tool_dir.mkdir()
        (tool_dir / "tool.yaml").write_text("- not: a mapping\n")
        loader = ToolLoader()
        with pytest.raises(ValueError, match="YAML mapping"):
            loader.load(tool_dir)

    def test_load_unknown_type_raises(self, tmp_path):
        tool_dir = tmp_path / "bad_type"
        tool_dir.mkdir()
        (tool_dir / "tool.yaml").write_text(
            yaml.dump({"name": "t", "type": "unknown_xyz", "config": {}})
        )
        loader = ToolLoader()
        with pytest.raises(KeyError, match="Unknown tool type"):
            loader.load(tool_dir)

    def test_load_all_empty_dir(self, tmp_path):
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        loader = ToolLoader()
        assert loader.load_all(tools_dir) == []

    def test_load_all_missing_dir_raises(self, tmp_path):
        loader = ToolLoader()
        with pytest.raises(FileNotFoundError):
            loader.load_all(tmp_path / "nonexistent")

    def test_load_all_skips_files(self, tmp_path):
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        (tools_dir / "readme.txt").write_text("ignore me")
        loader = ToolLoader()
        assert loader.load_all(tools_dir) == []

    def test_load_function_tool(self, sample_function_tool_dir):
        """Full integration: load a function-type tool directory."""
        tools_dir = sample_function_tool_dir.parent
        loader = ToolLoader()
        defs = loader.load_all(tools_dir)
        assert len(defs) == 1
        defn = defs[0]
        assert defn.name == "function_tool"
        assert defn.type == "function"
        assert defn.proto_input is not None
        assert defn.proto_output is not None
