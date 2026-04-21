"""
ProtoSchemaConverter — converts a :class:`~agent_tools.proto.descriptor.ProtoDescriptor`
into a JSON Schema dict suitable for LLM / ADK tool declarations.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from google.protobuf.descriptor import FieldDescriptor

if TYPE_CHECKING:
    from agent_tools.proto.descriptor import ProtoDescriptor

# Mapping from protobuf scalar field types to JSON Schema primitives
_SCALAR_TYPE_MAP: dict[int, dict[str, str]] = {
    FieldDescriptor.TYPE_STRING:   {"type": "string"},
    FieldDescriptor.TYPE_BYTES:    {"type": "string", "format": "byte"},
    FieldDescriptor.TYPE_BOOL:     {"type": "boolean"},
    FieldDescriptor.TYPE_INT32:    {"type": "integer"},
    FieldDescriptor.TYPE_INT64:    {"type": "integer"},
    FieldDescriptor.TYPE_UINT32:   {"type": "integer"},
    FieldDescriptor.TYPE_UINT64:   {"type": "integer"},
    FieldDescriptor.TYPE_SINT32:   {"type": "integer"},
    FieldDescriptor.TYPE_SINT64:   {"type": "integer"},
    FieldDescriptor.TYPE_FIXED32:  {"type": "integer"},
    FieldDescriptor.TYPE_FIXED64:  {"type": "integer"},
    FieldDescriptor.TYPE_SFIXED32: {"type": "integer"},
    FieldDescriptor.TYPE_SFIXED64: {"type": "integer"},
    FieldDescriptor.TYPE_FLOAT:    {"type": "number"},
    FieldDescriptor.TYPE_DOUBLE:   {"type": "number"},
}


def _is_repeated(field: Any) -> bool:
    """Return True if *field* is a repeated (list) field.

    Protobuf ≥ 4.x exposes ``field.is_repeated`` as a bool property; older
    versions expose it as a callable.  We handle both, and fall back to the
    (now-deprecated) ``LABEL_REPEATED`` comparison only when neither exists.
    """
    if hasattr(field, "is_repeated"):
        attr = field.is_repeated
        return attr() if callable(attr) else bool(attr)
    return field.label == FieldDescriptor.LABEL_REPEATED  # type: ignore[attr-defined]


class ProtoSchemaConverter:
    """Derives JSON Schema from a compiled proto descriptor."""

    @staticmethod
    def to_json_schema(descriptor: "ProtoDescriptor") -> dict[str, Any]:
        """
        Convert the message defined by *descriptor* into a JSON Schema object.

        Top-level non-optional fields are added to the ``required`` array.
        """
        properties: dict[str, Any] = {}
        required: list[str] = []

        for field in descriptor.message_class.DESCRIPTOR.fields:
            properties[field.name] = ProtoSchemaConverter._field_schema(field)
            # In proto3 every scalar field has a zero default, so technically
            # all fields are optional.  We mark non-message, non-repeated
            # fields as required to give LLMs better guidance.
            if (
                not _is_repeated(field)
                and field.type != FieldDescriptor.TYPE_MESSAGE
            ):
                required.append(field.name)

        schema: dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required
        return schema

    @staticmethod
    def _field_schema(field: Any) -> dict[str, Any]:
        """Return the JSON Schema snippet for a single proto field."""
        if field.type == FieldDescriptor.TYPE_MESSAGE:
            # Nested message — recurse
            nested: dict[str, Any] = {
                "type": "object",
                "properties": {
                    f.name: ProtoSchemaConverter._field_schema(f)
                    for f in field.message_type.fields
                },
            }
            if _is_repeated(field):
                return {"type": "array", "items": nested}
            return nested

        if field.type == FieldDescriptor.TYPE_ENUM:
            enum_values = [v.name for v in field.enum_type.values]
            base: dict[str, Any] = {"type": "string", "enum": enum_values}
            if _is_repeated(field):
                return {"type": "array", "items": base}
            return base

        base_schema = _SCALAR_TYPE_MAP.get(field.type, {"type": "string"}).copy()
        if _is_repeated(field):
            return {"type": "array", "items": base_schema}
        return base_schema
