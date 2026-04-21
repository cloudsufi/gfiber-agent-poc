"""Unit tests for agent_tools.proto.descriptor."""
from __future__ import annotations

from pathlib import Path

import pytest

from agent_tools.proto.loader import ProtoLoader


@pytest.fixture()
def simple_descriptor(tmp_path):
    proto = tmp_path / "thing.proto"
    proto.write_text(
        'syntax = "proto3";\n'
        "message Thing {\n"
        "  string name = 1;\n"
        "  int32  count = 2;\n"
        "}\n"
    )
    loader = ProtoLoader()
    return loader.load(proto)


class TestProtoDescriptor:
    def test_message_class_found(self, simple_descriptor):
        cls = simple_descriptor.message_class
        assert cls.__name__ == "Thing"

    def test_from_dict_valid(self, simple_descriptor):
        msg = simple_descriptor.from_dict({"name": "test", "count": 3})
        assert msg.name == "test"
        assert msg.count == 3

    def test_from_dict_unknown_field_raises(self, simple_descriptor):
        from google.protobuf.json_format import ParseError
        with pytest.raises((ParseError, Exception)):
            simple_descriptor.from_dict({"unknown_field": "x"})

    def test_to_dict_round_trip(self, simple_descriptor):
        data = {"name": "hello", "count": 7}
        msg = simple_descriptor.from_dict(data)
        result = simple_descriptor.to_dict(msg)
        assert result["name"] == "hello"
        assert result["count"] == 7

    def test_create(self, simple_descriptor):
        msg = simple_descriptor.create(name="direct", count=1)
        assert msg.name == "direct"

    def test_repr(self, simple_descriptor):
        r = repr(simple_descriptor)
        assert "thing.proto" in r
