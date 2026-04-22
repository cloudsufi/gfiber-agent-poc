"""
Validates the ``config:`` block of a ``tool.yaml`` against the tool type's
proto schema at load time (not at call time).

Why proto for config
--------------------
Using a ``.proto`` schema for the YAML config gives three compile-time-ish
guarantees without writing any Python validator code:

1. **Typed field access** — ``timeout_seconds: "10"`` (string) will fail
   because protobuf knows the field is ``int32``.
2. **No silent typos** — ``methd: GET`` instead of ``method: GET`` raises
   "unknown field methd" instead of silently using the default verb.
3. **Required vs. optional** — fields are as documented in the proto file,
   with no extra Python-level convention layer to get out of sync.

Validation is a round-trip: dict → Message → dict. The returned dict is
the **normalized** form (field names canonicalized, defaults filled in)
that the runtime actually stores on :class:`ToolDefinition`.
"""
from __future__ import annotations

from typing import Any

from agent_tools.core.definition import ToolTypeEntry
from agent_tools.proto.descriptor import ProtoDescriptor
from agent_tools.proto.loader import ProtoLoader


class ConfigValidator:
    """
    Compiles each tool type's config ``.proto`` schema on first use (cached),
    then validates every ``config:`` dict through it.

    Raises :class:`ValueError` with a human-readable message on any violation:
    missing required field, unknown field, or wrong field type.
    """

    def __init__(self) -> None:
        self._proto_loader = ProtoLoader()
        self._schema_cache: dict[str, ProtoDescriptor] = {}

    def validate(
        self,
        tool_name: str,
        config: dict[str, Any],
        entry: ToolTypeEntry,
    ) -> dict[str, Any]:
        """
        Parse *config* through the type's proto schema and return the
        round-tripped (cleaned / normalised) dict.

        :raises ValueError: on schema violation.
        :raises FileNotFoundError: if the config schema proto is missing.
        """
        descriptor = self._get_schema(entry)
        try:
            message = descriptor.from_dict(config)
            return descriptor.to_dict(message)
        except Exception as exc:
            raise ValueError(
                f"Tool '{tool_name}' (type={entry.name}): invalid config — {exc}\n"
                f"Expected schema: {entry.config_proto_path}"
            ) from exc

    def _get_schema(self, entry: ToolTypeEntry) -> ProtoDescriptor:
        key = str(entry.config_proto_path)
        if key not in self._schema_cache:
            descriptor = self._proto_loader.load(entry.config_proto_path)
            if descriptor is None:
                raise FileNotFoundError(
                    f"Config schema not found: {entry.config_proto_path}"
                )
            self._schema_cache[key] = descriptor
        return self._schema_cache[key]
