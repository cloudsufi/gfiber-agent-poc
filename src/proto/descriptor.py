"""
ProtoDescriptor — typed wrapper over a compiled ``_pb2`` module.

What :class:`ProtoLoader` returns isn't a raw Python module but a
:class:`ProtoDescriptor` — a thin dataclass that caches the "primary"
message class of the module and offers two ergonomic helpers:

* ``from_dict(data, ignore_unknown=False)`` — parses a plain Python dict
  into a protobuf ``Message`` instance. Wraps
  ``google.protobuf.json_format.ParseDict``.
* ``to_dict(message)`` — converts a ``Message`` back into a dict with
  snake_case field names preserved (the default in that library is
  camelCase, which we override).

The "primary message" is the first :class:`google.protobuf.message.Message`
subclass defined in the module. In practice each tool's
``request.proto`` / ``response.proto`` declares exactly one top-level
message, so this assumption holds cleanly. Files with multiple top-level
messages would need explicit class selection.
"""
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

    def from_dict(
        self,
        data: dict[str, Any],
        *,
        ignore_unknown: bool = False,
    ) -> Message:
        """
        Parse *data* into a :class:`~google.protobuf.message.Message`.

        :param ignore_unknown: when True, silently drop fields that aren't
            declared in the proto. Useful when validating responses from
            external APIs whose schema you don't fully mirror.
        :raises google.protobuf.json_format.ParseError: on schema violation.
        """
        from google.protobuf.json_format import ParseDict

        return ParseDict(
            data,
            self.message_class(),
            ignore_unknown_fields=ignore_unknown,
        )

    def to_dict(self, message: Message) -> dict[str, Any]:
        """
        Serialise *message* to a plain Python ``dict``.

        Field names are preserved as declared in the ``.proto``
        (snake_case). The default of ``google.protobuf.json_format`` is to
        camelCase field names, which would break all the places in the
        framework that index dicts by proto field name.
        """
        from google.protobuf.json_format import MessageToDict

        return MessageToDict(message, preserving_proto_field_name=True)

    def create(self, **kwargs: Any) -> Message:
        """
        Convenience constructor — ``descriptor.create(field=value)``.

        Equivalent to calling the underlying message class directly; useful
        when you want to build a message without importing the ``_pb2``
        module yourself.
        """
        return self.message_class(**kwargs)

    def __repr__(self) -> str:
        return f"ProtoDescriptor(proto={self.proto_path.name})"
