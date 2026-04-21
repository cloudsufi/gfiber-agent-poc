"""Unit tests for agent_tools.proto.converter."""
from __future__ import annotations

import pytest

from agent_tools.proto.loader import ProtoLoader
from agent_tools.proto.converter import ProtoSchemaConverter


@pytest.fixture()
def full_descriptor(tmp_path):
    proto = tmp_path / "full.proto"
    proto.write_text(
        'syntax = "proto3";\n'
        "message Full {\n"
        "  string name      = 1;\n"
        "  int32  age       = 2;\n"
        "  bool   active    = 3;\n"
        "  double score     = 4;\n"
        "  repeated string tags = 5;\n"
        "}\n"
    )
    return ProtoLoader().load(proto)


class TestProtoSchemaConverter:
    def test_type_is_object(self, full_descriptor):
        schema = ProtoSchemaConverter.to_json_schema(full_descriptor)
        assert schema["type"] == "object"

    def test_string_field(self, full_descriptor):
        props = ProtoSchemaConverter.to_json_schema(full_descriptor)["properties"]
        assert props["name"] == {"type": "string"}

    def test_int_field(self, full_descriptor):
        props = ProtoSchemaConverter.to_json_schema(full_descriptor)["properties"]
        assert props["age"] == {"type": "integer"}

    def test_bool_field(self, full_descriptor):
        props = ProtoSchemaConverter.to_json_schema(full_descriptor)["properties"]
        assert props["active"] == {"type": "boolean"}

    def test_double_field(self, full_descriptor):
        props = ProtoSchemaConverter.to_json_schema(full_descriptor)["properties"]
        assert props["score"] == {"type": "number"}

    def test_repeated_field(self, full_descriptor):
        props = ProtoSchemaConverter.to_json_schema(full_descriptor)["properties"]
        assert props["tags"] == {"type": "array", "items": {"type": "string"}}

    def test_required_contains_scalars(self, full_descriptor):
        schema = ProtoSchemaConverter.to_json_schema(full_descriptor)
        assert "required" in schema
        assert "name" in schema["required"]
        assert "age" in schema["required"]
