"""Unit tests for agent_tools.schema.converter.to_llm_schema."""

from __future__ import annotations

from agent_tools.schema.converter import to_llm_schema


class TestToLlmSchema:
    def test_none_returns_empty_object_schema(self):
        assert to_llm_schema(None) == {"type": "object", "properties": {}}

    def test_empty_dict_gets_defaults(self):
        assert to_llm_schema({}) == {"type": "object", "properties": {}}

    def test_strips_dollar_schema_and_title(self):
        out = to_llm_schema(
            {
                "$schema": "http://json-schema.org/draft-07/schema#",
                "title": "Foo",
                "type": "object",
                "properties": {"x": {"type": "string"}},
            }
        )
        assert out == {
            "type": "object",
            "properties": {"x": {"type": "string"}},
        }

    def test_preserves_required_and_nested(self):
        out = to_llm_schema(
            {
                "type": "object",
                "required": ["x"],
                "properties": {
                    "x": {"type": "string"},
                    "nested": {
                        "type": "object",
                        "properties": {"y": {"type": "integer"}},
                    },
                },
            }
        )
        assert out["required"] == ["x"]
        assert out["properties"]["nested"]["properties"]["y"] == {"type": "integer"}
