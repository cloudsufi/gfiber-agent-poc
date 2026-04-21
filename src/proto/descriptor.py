"""ProtoDescriptor — typed wrapper over a compiled ``_pb2`` module."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Type

from google.protobuf.message import Message


@dataclass
class ProtoDescriptor:
    """
    Wraps a compiled ``_pb2`` module produced by :class:`~agent_tools.proto.loader.ProtoLoader`.

    Provides high-level ``from_dict`` / ``to_dict`` helpers and exposes the
    first :class:`~google.protobuf.message.Message` subclass in the module.
    """

    module: Any   # compiled *_pb2 module
    proto_path: Path

    # ── Message class ─────────────────────────────────────────────────────────

    @property
    def message_class(self) -> Type[Message]:
        """Return the first ``Message`` subclass defined in the compiled module."""
        for attr in dir(self.module):
            obj = getattr(self.module, attr)
            try:
                if isinstance(obj, type) and issubclass(obj, Message) and obj is not Message:
                    return obj
            except TypeError:
                pass
        raise RuntimeError(
            f"No protobuf Message class found in compiled module for {self.proto_path}"
        )

    # ── Conversion helpers ────────────────────────────────────────────────────

    def from_dict(self, data: dict[str, Any]) -> Message:
        """
        Parse *data* into a :class:`~google.protobuf.message.Message`.

        :raises google.protobuf.json_format.ParseError: on schema violation.
        """
        from google.protobuf.json_format import ParseDict

        return ParseDict(data, self.message_class())

    def to_dict(self, message: Message) -> dict[str, Any]:
        """
        Serialise *message* to a plain Python ``dict``.

        Field names are preserved as declared in the ``.proto`` (snake_case).
        """
        from google.protobuf.json_format import MessageToDict

        return MessageToDict(message, preserving_proto_field_name=True)

    def create(self, **kwargs: Any) -> Message:
        """Convenience constructor — ``descriptor.create(field=value)``."""
        return self.message_class(**kwargs)

    def __repr__(self) -> str:
        return f"ProtoDescriptor(proto={self.proto_path.name})"
