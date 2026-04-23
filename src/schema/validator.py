"""
Validation helpers wrapping :mod:`jsonschema`.

Two entry points
----------------
* :func:`validate_input` — strict. Rejects unknown fields *if* the schema
  sets ``additionalProperties: false``, enforces required fields, and
  checks types. Used by :class:`ConfigValidator` (for tool.yaml config
  blocks) and by :class:`SchemaValidationMiddleware` for request
  input.

* :func:`validate_output` — lenient. Keeps only declared top-level fields
  before validating, so extras returned by external APIs don't fail the
  contract. Used on handler return values.

Error handling
--------------
Both functions raise a plain :class:`ValueError` rather than letting
``jsonschema.ValidationError`` bubble up. The message is built from the
offending path + reason so the caller sees something like::

    invalid input at 'customer_id': 42 is not of type 'string'
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from jsonschema import Draft7Validator


def validate_input(data: Mapping[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    """
    Validate *data* against *schema* strictly.

    Returns the validated data as a dict. If *schema* declares
    ``additionalProperties: false`` (the convention used by this
    framework's config and request schemas), unknown keys raise.

    :raises ValueError: on validation failure.
    """
    validator = Draft7Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    if errors:
        raise ValueError(_format_errors(errors))
    return dict(data)


def validate_output(data: Any, schema: dict[str, Any]) -> Any:
    """
    Validate *data* against *schema* leniently.

    Only top-level fields declared in the schema's ``properties`` are kept —
    anything else returned by the handler is dropped. This mirrors the
    behaviour we need for external APIs (httpbin, GCP, vendor APIs) that
    routinely return fields we don't model.

    Non-dict return values (lists, scalars) are handled by strict
    :class:`jsonschema` validation — ``additionalProperties`` only applies
    to objects so there's nothing to strip.

    :raises ValueError: if the declared fields that ARE present fail
        type / format validation.
    """
    if isinstance(data, dict):
        declared = set(schema.get("properties", {}).keys())
        filtered: dict[str, Any] = {k: v for k, v in data.items() if k in declared}
    else:
        filtered = data

    validator = Draft7Validator(schema)
    errors = sorted(validator.iter_errors(filtered), key=lambda e: list(e.absolute_path))
    if errors:
        raise ValueError(_format_errors(errors))
    return filtered


def _format_errors(errors: list) -> str:  # type: ignore[type-arg]
    """Turn one-or-more ValidationError objects into a single human message."""
    parts: list[str] = []
    for err in errors:
        path = "/".join(str(p) for p in err.absolute_path) or "<root>"
        parts.append(f"at '{path}': {err.message}")
    return "; ".join(parts)
