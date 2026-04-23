"""Unit tests for agent_tools.schema.loader."""

from __future__ import annotations

import pytest
from agent_tools.schema.loader import SchemaLoader


class TestSchemaLoader:
    def test_returns_none_for_missing_file(self, tmp_path):
        assert SchemaLoader().load(tmp_path / "nope.yaml") is None

    def test_loads_valid_yaml_schema(self, tmp_path):
        p = tmp_path / "s.yaml"
        p.write_text("type: object\nproperties:\n  name: {type: string}\n")
        schema = SchemaLoader().load(p)
        assert schema == {
            "type": "object",
            "properties": {"name": {"type": "string"}},
        }

    def test_cache_returns_same_object(self, tmp_path):
        p = tmp_path / "s.yaml"
        p.write_text("type: object\n")
        loader = SchemaLoader()
        first = loader.load(p)
        second = loader.load(p)
        assert first is second

    def test_non_mapping_raises(self, tmp_path):
        p = tmp_path / "bad.yaml"
        p.write_text("- not\n- a\n- mapping\n")
        with pytest.raises(ValueError, match="mapping"):
            SchemaLoader().load(p)

    def test_empty_file_is_empty_dict(self, tmp_path):
        p = tmp_path / "empty.yaml"
        p.write_text("")
        assert SchemaLoader().load(p) == {}
