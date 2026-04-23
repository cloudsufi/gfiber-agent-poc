"""
Schema loader — reads a YAML / JSON-Schema file from disk and returns the
parsed dict. Result is cached per absolute path so repeated loads during a
tool-directory scan are free.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class SchemaLoader:
    """
    Load YAML schema files and cache the parsed dicts.

    Why cache
    ---------
    Config schemas (``api_tool_config.yaml`` etc.) are read once per
    process but referenced by every tool of that type. Request/response
    schemas are per-tool, so the cache helps less for them but costs
    nothing.
    """

    def __init__(self) -> None:
        self._cache: dict[str, dict[str, Any]] = {}

    def load(self, schema_path: Path) -> dict[str, Any] | None:
        """
        Parse *schema_path* as YAML and return the schema dict.

        :returns: The parsed schema, or ``None`` if the file doesn't exist
            (tools may omit ``request.yaml`` / ``response.yaml`` to opt
            out of that validation step).
        :raises ValueError: if the YAML file exists but isn't a mapping.
        """
        if not schema_path.exists():
            return None

        key = str(schema_path.resolve())
        if key in self._cache:
            return self._cache[key]

        with open(schema_path) as fh:
            data = yaml.safe_load(fh)
        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise ValueError(
                f"Schema file must contain a YAML mapping, got {type(data).__name__}: {schema_path}"
            )

        self._cache[key] = data
        return data
