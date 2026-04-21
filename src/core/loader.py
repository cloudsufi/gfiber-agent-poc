"""
Loads tool directories into validated :class:`~agent_tools.core.definition.ToolDefinition`
objects.  All work happens at startup — synchronous, fail-fast.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from agent_tools.core.config_validator import ConfigValidator
from agent_tools.core.definition import ExecutionConfig, ToolDefinition
from agent_tools.core.type_registry import ToolTypeRegistry, default_type_registry
from agent_tools.proto.loader import ProtoLoader


class ToolLoader:
    """
    For every sub-directory under *tools_dir* that contains a ``tool.yaml``:

    1. Parse ``tool.yaml``
    2. Resolve handler + config schema via :class:`ToolTypeRegistry`
    3. Validate ``config:`` block via :class:`ConfigValidator` (proto-enforced)
    4. Compile ``request.proto`` + ``response.proto`` (optional)
    5. Return a fully-resolved :class:`ToolDefinition`

    Any config violation raises :class:`ValueError` at step 3 — tools are never
    silently broken at call time.
    """

    def __init__(
        self,
        type_registry: ToolTypeRegistry = default_type_registry,
    ) -> None:
        self._type_registry = type_registry
        self._config_validator = ConfigValidator()
        self._proto_loader = ProtoLoader()

    # ── public ────────────────────────────────────────────────────────────────

    def load(self, tool_dir: Path) -> ToolDefinition:
        """Load a single tool directory and return a :class:`ToolDefinition`."""
        raw = self._read_yaml(tool_dir / "tool.yaml")
        tool_name = raw["name"]
        tool_type = raw["type"]

        type_entry = self._type_registry.get(tool_type)

        # Validate config block against type-specific proto schema
        validated_config = self._config_validator.validate(
            tool_name, raw.get("config", {}), type_entry
        )

        return ToolDefinition(
            name=tool_name,
            version=raw.get("version", "1.0"),
            type=tool_type,
            description=raw.get("description", ""),
            config=validated_config,
            execution=ExecutionConfig(
                retries=raw.get("execution", {}).get("retries", -1),
                timeout=raw.get("execution", {}).get("timeout", -1),
            ),
            handler_class=type_entry.handler_class,
            proto_input=self._proto_loader.load(tool_dir / "request.proto"),
            proto_output=self._proto_loader.load(tool_dir / "response.proto"),
            tool_dir=tool_dir,
        )

    def load_all(self, tools_dir: Path) -> list[ToolDefinition]:
        """
        Scan *tools_dir* for sub-directories containing ``tool.yaml`` and load
        each one.  Returns definitions in directory-name order.
        """
        if not tools_dir.is_dir():
            raise FileNotFoundError(f"tools_dir not found: {tools_dir}")

        definitions: list[ToolDefinition] = []
        for tool_dir in sorted(tools_dir.iterdir()):
            if tool_dir.is_dir() and (tool_dir / "tool.yaml").exists():
                definitions.append(self.load(tool_dir))
        return definitions

    # ── private ───────────────────────────────────────────────────────────────

    @staticmethod
    def _read_yaml(path: Path) -> dict:
        if not path.exists():
            raise FileNotFoundError(f"tool.yaml not found: {path}")
        with open(path) as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, dict):
            raise ValueError(f"tool.yaml must be a YAML mapping: {path}")
        return data
