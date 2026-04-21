"""Core data-classes that describe a tool's fully-resolved contract."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_tools.core.settings import Settings
    from agent_tools.proto.descriptor import ProtoDescriptor


@dataclass
class ExecutionConfig:
    """
    Per-tool retry / timeout overrides.

    ``-1`` is the sentinel meaning "use the :class:`Settings` default".
    Call :meth:`resolved` to fill sentinels before executing.
    """

    retries: int = -1
    timeout: int = -1

    def resolved(self, settings: "Settings") -> "ExecutionConfig":
        """Return a new :class:`ExecutionConfig` with sentinels replaced."""
        return ExecutionConfig(
            retries=self.retries if self.retries >= 0 else settings.default_retries,
            timeout=self.timeout if self.timeout >= 0 else settings.default_timeout,
        )


@dataclass
class ToolTypeEntry:
    """Associates a tool type name with its config schema path and handler class."""

    name: str
    config_proto_path: Path
    handler_class: Any  # type: ignore[misc]


@dataclass
class ToolDefinition:
    """
    Fully-resolved, config-validated description of a single tool.

    Created by :class:`~agent_tools.core.loader.ToolLoader` at startup.
    """

    name: str
    version: str
    type: str
    description: str
    config: dict[str, Any]
    execution: ExecutionConfig
    handler_class: Any  # type: ignore[misc]
    proto_input: "ProtoDescriptor | None" = field(default=None, repr=False)
    proto_output: "ProtoDescriptor | None" = field(default=None, repr=False)
    tool_dir: Path | None = None

    @property
    def adk_schema(self) -> dict[str, Any]:
        """
        Return the JSON-Schema dict required by ADK / LLM framework tool declarations.

        Derived automatically from ``request.proto`` if present; otherwise an
        empty-object schema is returned.
        """
        from agent_tools.proto.converter import ProtoSchemaConverter

        params = (
            ProtoSchemaConverter.to_json_schema(self.proto_input)
            if self.proto_input
            else {"type": "object", "properties": {}}
        )
        return {
            "name": self.name,
            "description": self.description,
            "parameters": params,
        }
