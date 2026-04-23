"""
Schema converter — turns a request schema into the JSON-Schema form that
ADK / LLM frameworks expect on a tool declaration.

Since our schemas are already JSON Schema, this is almost a pass-through.
We strip a few informational fields (``$schema``, ``title``, top-level
``description``) so the result is the bare object expected as the
``parameters`` field of an ADK ``FunctionDeclaration``.
"""

from __future__ import annotations

from typing import Any

_STRIPPED_KEYS = {"$schema", "title"}


def to_llm_schema(schema: dict[str, Any] | None) -> dict[str, Any]:
    """
    Return *schema* with metadata fields removed.

    ``None`` input → ``{"type": "object", "properties": {}}`` so tools
    that omit a request schema still get a valid empty parameter block.
    """
    if not schema:
        return {"type": "object", "properties": {}}

    cleaned = {k: v for k, v in schema.items() if k not in _STRIPPED_KEYS}
    # Ensure top-level type defaults to object — LLMs expect that shape.
    cleaned.setdefault("type", "object")
    cleaned.setdefault("properties", {})
    return cleaned
