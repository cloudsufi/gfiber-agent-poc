"""Unit tests for agent_tools.proto.loader."""
from __future__ import annotations

from pathlib import Path

import pytest

from agent_tools.proto.loader import ProtoLoader


class TestProtoLoader:
    def test_returns_none_for_missing_file(self, tmp_path):
        loader = ProtoLoader()
        result = loader.load(tmp_path / "nonexistent.proto")
        assert result is None

    def test_compiles_valid_proto(self, tmp_path):
        proto = tmp_path / "simple.proto"
        proto.write_text('syntax = "proto3";\nmessage Ping { string msg = 1; }\n')
        loader = ProtoLoader()
        descriptor = loader.load(proto)
        assert descriptor is not None
        assert descriptor.proto_path == proto

    def test_result_is_cached(self, tmp_path):
        proto = tmp_path / "cached.proto"
        proto.write_text('syntax = "proto3";\nmessage C { string v = 1; }\n')
        loader = ProtoLoader()
        d1 = loader.load(proto)
        d2 = loader.load(proto)
        assert d1 is d2   # exact same object from cache

    def test_invalid_proto_raises(self, tmp_path):
        proto = tmp_path / "bad.proto"
        proto.write_text("this is not valid protobuf !!!")
        loader = ProtoLoader()
        with pytest.raises(RuntimeError, match="protoc failed"):
            loader.load(proto)
