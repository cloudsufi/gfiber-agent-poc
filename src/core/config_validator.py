"""
Validates the ``config:`` block of a ``tool.yaml`` against the tool type's
YAML schema at load time (not at call time).

Why schema-validate at load time
--------------------------------
* **Typo detection** — ``methd: GET`` instead of ``method: GET`` is caught
  immediately, not papered over with a silent default.
* **Type enforcement** — ``timeout_seconds: "10"`` (string) fails because
  the schema says ``integer``.
* **Required fields** — missing ``endpoint`` on an ``api`` tool blocks
  framework import rather than failing on the first call.

Validation is done by :mod:`jsonschema` (pure Python, no compile step).
The returned dict is the input itself — jsonschema doesn't normalize, so
field names and values come back exactly as declared in the user's yaml.
"""

from __future__ import annotations

from typing import Any

from agent_tools.core.definition import ToolTypeEntry
from agent_tools.schema.loader import SchemaLoader
from agent_tools.schema.validator import validate_input


class ConfigValidator:
    """
    Loads each tool type's config schema on first use (cached) and
    validates every ``config:`` dict through it.

    Raises :class:`ValueError` with a human-readable message on any
    violation — missing required field, unknown field, or wrong type.
    """

    def __init__(self) -> None:
        self._schema_loader = SchemaLoader()
        self._schema_cache: dict[str, dict[str, Any]] = {}

    def validate(
        self,
        tool_name: str,
        config: dict[str, Any],
        entry: ToolTypeEntry,
    ) -> dict[str, Any]:
        """
        Validate *config* against the type's YAML schema and return it.

        :raises ValueError: on schema violation.
        :raises FileNotFoundError: if the config schema file is missing.
        """
        schema = self._get_schema(entry)
        try:
            return validate_input(config, schema)
        except ValueError as exc:
            raise ValueError(
                f"Tool '{tool_name}' (type={entry.name}): invalid config — {exc}\n"
                f"Expected schema: {entry.config_schema_path}"
            ) from exc

    def _get_schema(self, entry: ToolTypeEntry) -> dict[str, Any]:
        key = str(entry.config_schema_path)
        if key not in self._schema_cache:
            schema = self._schema_loader.load(entry.config_schema_path)
            if schema is None:
                raise FileNotFoundError(f"Config schema not found: {entry.config_schema_path}")
            self._schema_cache[key] = schema
        return self._schema_cache[key]
