"""Default type registry — the primary types are always present."""

from __future__ import annotations

from agent_tools.core.type_registry import default_type_registry


class TestDefaultTypeRegistry:
    def test_api_registered(self):
        assert "api" in default_type_registry

    def test_mcp_registered(self):
        assert "mcp" in default_type_registry

    def test_function_registered(self):
        assert "function" in default_type_registry

    def test_cta_registered(self):
        assert "cta" in default_type_registry

    def test_openapi_registered(self):
        assert "openapi" in default_type_registry

    def test_primary_types_all_present(self):
        for name in ("api", "mcp", "function", "cta", "openapi"):
            entry = default_type_registry.get(name)
            assert entry.name == name
            assert entry.config_schema_path.exists()
            assert entry.handler_class is not None

    def test_five_types_registered(self):
        assert default_type_registry.known_types() == ["api", "cta", "function", "mcp", "openapi"]
