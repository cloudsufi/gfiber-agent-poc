"""Unit tests for agent_tools.schema.validator."""

from __future__ import annotations

import pytest
from agent_tools.schema.validator import validate_input, validate_output

STRICT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["name", "count"],
    "properties": {
        "name": {"type": "string"},
        "count": {"type": "integer", "minimum": 0},
    },
}

LENIENT_SCHEMA = {
    "type": "object",
    "properties": {
        "result": {"type": "string"},
        "score": {"type": "number"},
    },
}


class TestValidateInput:
    def test_valid_input_returns_dict(self):
        result = validate_input({"name": "x", "count": 3}, STRICT_SCHEMA)
        assert result == {"name": "x", "count": 3}

    def test_missing_required_raises(self):
        with pytest.raises(ValueError, match="required"):
            validate_input({"name": "x"}, STRICT_SCHEMA)

    def test_unknown_field_raises(self):
        with pytest.raises(ValueError, match="not allowed"):
            validate_input({"name": "x", "count": 3, "rogue": 1}, STRICT_SCHEMA)

    def test_wrong_type_raises(self):
        with pytest.raises(ValueError, match="integer"):
            validate_input({"name": "x", "count": "three"}, STRICT_SCHEMA)

    def test_minimum_violation_raises(self):
        with pytest.raises(ValueError, match="minimum"):
            validate_input({"name": "x", "count": -1}, STRICT_SCHEMA)


class TestValidateOutput:
    def test_drops_undeclared_fields(self):
        out = validate_output(
            {"result": "ok", "rogue_from_api": 99},
            LENIENT_SCHEMA,
        )
        assert out == {"result": "ok"}

    def test_keeps_declared_fields(self):
        out = validate_output(
            {"result": "ok", "score": 0.9},
            LENIENT_SCHEMA,
        )
        assert out == {"result": "ok", "score": 0.9}

    def test_wrong_declared_type_raises(self):
        with pytest.raises(ValueError, match="string"):
            validate_output(
                {"result": 123},  # int not string
                LENIENT_SCHEMA,
            )

    def test_scalar_pass_through(self):
        """Non-dict returns are handed to jsonschema as-is."""
        assert validate_output("ok", {"type": "string"}) == "ok"
