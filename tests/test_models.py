"""
Tests for adk_tools/models.py

Covers:
- All auth config models (happy path + every validator branch)
- All tool config models (happy path + validators)
- ToolDef parsing
- load_tool_def() — file existence checks, YAML errors, schema meta-validation
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from adk_tools.models import (
    APIKeyAuthConfig,
    BearerAuthConfig,
    FunctionConfig,
    MCPConfig,
    OAuth2AuthConfig,
    OpenAPIConfig,
    ServiceAccountAuthConfig,
    ToolDef,
    load_tool_def,
)


# ── BearerAuthConfig ───────────────────────────────────────────────────────────

class TestBearerAuthConfig:
    def test_env_ok(self):
        cfg = BearerAuthConfig(type="bearer", token_env="MY_TOKEN")
        assert cfg.token_env == "MY_TOKEN"
        assert cfg.token_secret is None

    def test_secret_ok(self):
        cfg = BearerAuthConfig(type="bearer", token_secret="projects/p/secrets/s/versions/latest")
        assert cfg.token_secret is not None
        assert cfg.token_env is None

    def test_neither_raises(self):
        with pytest.raises(ValidationError, match="token_env.*token_secret|token_env' or 'token_secret"):
            BearerAuthConfig(type="bearer")

    def test_both_raises(self):
        with pytest.raises(ValidationError, match="OR"):
            BearerAuthConfig(type="bearer", token_env="A", token_secret="B")

    def test_extra_field_raises(self):
        with pytest.raises(ValidationError):
            BearerAuthConfig(type="bearer", token_env="X", unknown_field="y")


# ── APIKeyAuthConfig ───────────────────────────────────────────────────────────

class TestAPIKeyAuthConfig:
    def test_env_ok_defaults(self):
        cfg = APIKeyAuthConfig(type="api_key", key_env="API_KEY")
        assert cfg.header_name == "X-API-Key"
        assert cfg.location == "header"

    def test_secret_ok(self):
        cfg = APIKeyAuthConfig(type="api_key", key_secret="projects/p/secrets/k/versions/1")
        assert cfg.key_secret is not None

    def test_custom_header_query(self):
        cfg = APIKeyAuthConfig(type="api_key", key_env="K", header_name="X-Custom", location="query")
        assert cfg.header_name == "X-Custom"
        assert cfg.location == "query"

    def test_neither_raises(self):
        with pytest.raises(ValidationError):
            APIKeyAuthConfig(type="api_key")

    def test_both_raises(self):
        with pytest.raises(ValidationError, match="OR"):
            APIKeyAuthConfig(type="api_key", key_env="A", key_secret="B")

    def test_invalid_location(self):
        with pytest.raises(ValidationError):
            APIKeyAuthConfig(type="api_key", key_env="K", location="body")


# ── OAuth2AuthConfig ───────────────────────────────────────────────────────────

class TestOAuth2AuthConfig:
    def test_env_ok(self):
        cfg = OAuth2AuthConfig(
            type="oauth2",
            client_id_env="CID",
            client_secret_env="CSEC",
            token_url="https://auth.example.com/token",
        )
        assert cfg.scope == ""
        assert cfg.token_url == "https://auth.example.com/token"

    def test_secret_ok(self):
        cfg = OAuth2AuthConfig(
            type="oauth2",
            client_id_secret="projects/p/secrets/cid/versions/1",
            client_secret_secret="projects/p/secrets/csec/versions/1",
            token_url="https://auth.example.com/token",
            scope="read:all",
        )
        assert cfg.scope == "read:all"

    def test_missing_client_id_raises(self):
        with pytest.raises(ValidationError):
            OAuth2AuthConfig(
                type="oauth2",
                client_secret_env="CSEC",
                token_url="https://auth.example.com/token",
            )

    def test_missing_client_secret_raises(self):
        with pytest.raises(ValidationError):
            OAuth2AuthConfig(
                type="oauth2",
                client_id_env="CID",
                token_url="https://auth.example.com/token",
            )

    def test_both_client_id_raises(self):
        with pytest.raises(ValidationError, match="OR"):
            OAuth2AuthConfig(
                type="oauth2",
                client_id_env="A",
                client_id_secret="B",
                client_secret_env="C",
                token_url="https://auth.example.com/token",
            )

    def test_both_client_secret_raises(self):
        with pytest.raises(ValidationError, match="OR"):
            OAuth2AuthConfig(
                type="oauth2",
                client_id_env="A",
                client_secret_env="C",
                client_secret_secret="D",
                token_url="https://auth.example.com/token",
            )

    def test_missing_token_url_raises(self):
        with pytest.raises(ValidationError):
            OAuth2AuthConfig(type="oauth2", client_id_env="A", client_secret_env="B")


# ── ServiceAccountAuthConfig ───────────────────────────────────────────────────

class TestServiceAccountAuthConfig:
    def test_env_ok(self):
        cfg = ServiceAccountAuthConfig(type="service_account", key_env="SA_JSON")
        assert cfg.scopes == ["https://www.googleapis.com/auth/cloud-platform"]
        assert cfg.audience == ""

    def test_secret_ok(self):
        cfg = ServiceAccountAuthConfig(
            type="service_account",
            key_secret="projects/p/secrets/sa/versions/latest",
            audience="https://myservice.example.com",
        )
        assert cfg.audience == "https://myservice.example.com"

    def test_neither_raises(self):
        with pytest.raises(ValidationError):
            ServiceAccountAuthConfig(type="service_account")

    def test_both_raises(self):
        with pytest.raises(ValidationError, match="OR"):
            ServiceAccountAuthConfig(type="service_account", key_env="A", key_secret="B")


# ── OpenAPIConfig ──────────────────────────────────────────────────────────────

class TestOpenAPIConfig:
    def test_defaults(self):
        cfg = OpenAPIConfig(type="openapi")
        assert cfg.spec_file == "openapi.yaml"
        assert cfg.auth is None
        assert cfg.timeout_seconds == 30

    def test_with_bearer_auth(self):
        cfg = OpenAPIConfig(
            type="openapi",
            auth={"type": "bearer", "token_env": "MY_TOKEN"},
        )
        assert isinstance(cfg.auth, BearerAuthConfig)

    def test_with_api_key_auth(self):
        cfg = OpenAPIConfig(
            type="openapi",
            auth={"type": "api_key", "key_env": "K"},
        )
        assert isinstance(cfg.auth, APIKeyAuthConfig)

    def test_negative_timeout_raises(self):
        with pytest.raises(ValidationError):
            OpenAPIConfig(type="openapi", timeout_seconds=-1)

    def test_extra_field_raises(self):
        with pytest.raises(ValidationError):
            OpenAPIConfig(type="openapi", unknown="x")


# ── MCPConfig ──────────────────────────────────────────────────────────────────

class TestMCPConfig:
    def test_sse_ok(self):
        cfg = MCPConfig(type="mcp", server_url="https://mcp.example.com/sse")
        assert cfg.server_url == "https://mcp.example.com/sse"
        assert cfg.command is None

    def test_stdio_ok(self):
        cfg = MCPConfig(type="mcp", command="python", args=["-m", "mcp_server"])
        assert cfg.command == "python"
        assert cfg.args == ["-m", "mcp_server"]

    def test_neither_raises(self):
        with pytest.raises(ValidationError, match="server_url.*command|requires either"):
            MCPConfig(type="mcp")

    def test_both_raises(self):
        with pytest.raises(ValidationError, match="not both|OR"):
            MCPConfig(type="mcp", server_url="https://x.com/sse", command="python")

    def test_tool_filter(self):
        cfg = MCPConfig(type="mcp", server_url="https://x.com/sse", tool_filter=["tool_a", "tool_b"])
        assert cfg.tool_filter == ["tool_a", "tool_b"]

    def test_env_vars(self):
        cfg = MCPConfig(type="mcp", command="node", env_vars={"LOG": "debug"})
        assert cfg.env_vars == {"LOG": "debug"}

    def test_with_bearer_auth(self):
        cfg = MCPConfig(
            type="mcp",
            server_url="https://mcp.example.com/sse",
            auth={"type": "bearer", "token_env": "MCP_TOKEN"},
        )
        assert isinstance(cfg.auth, BearerAuthConfig)


# ── FunctionConfig ─────────────────────────────────────────────────────────────

class TestFunctionConfig:
    def test_defaults(self):
        cfg = FunctionConfig(type="function")
        assert cfg.function == "run"
        assert cfg.parameters == {}

    def test_custom_function_name(self):
        cfg = FunctionConfig(type="function", function="my_handler")
        assert cfg.function == "my_handler"

    def test_parameters(self):
        cfg = FunctionConfig(type="function", parameters={"model": "v2", "threshold": "0.5"})
        assert cfg.parameters["model"] == "v2"

    def test_extra_field_raises(self):
        with pytest.raises(ValidationError):
            FunctionConfig(type="function", unknown="x")


# ── ToolDef ────────────────────────────────────────────────────────────────────

class TestToolDef:
    def test_openapi_tooldef(self):
        td = ToolDef.model_validate({
            "name": "my_api",
            "version": "2.0",
            "description": "My API tool",
            "config": {"type": "openapi", "spec_file": "spec.yaml"},
        })
        assert td.name == "my_api"
        assert isinstance(td.config, OpenAPIConfig)

    def test_function_tooldef(self):
        td = ToolDef.model_validate({
            "name": "my_fn",
            "config": {"type": "function"},
        })
        assert isinstance(td.config, FunctionConfig)
        assert td.version == "1.0"  # default

    def test_mcp_tooldef(self):
        td = ToolDef.model_validate({
            "name": "my_mcp",
            "config": {"type": "mcp", "server_url": "https://mcp.example.com/sse"},
        })
        assert isinstance(td.config, MCPConfig)

    def test_extra_fields_ignored(self):
        # ToolDef uses extra="ignore" so unknown top-level keys don't error
        td = ToolDef.model_validate({
            "name": "x",
            "config": {"type": "function"},
            "some_future_field": "value",
        })
        assert td.name == "x"

    def test_missing_config_raises(self):
        with pytest.raises(ValidationError):
            ToolDef.model_validate({"name": "x"})

    def test_discriminator_wrong_type_raises(self):
        with pytest.raises(ValidationError):
            ToolDef.model_validate({"name": "x", "config": {"type": "unsupported"}})


# ── load_tool_def ──────────────────────────────────────────────────────────────

class TestLoadToolDef:
    def _write_tool(self, tool_dir: Path, data: dict) -> None:
        (tool_dir / "tool.yaml").write_text(yaml.dump(data))

    def test_openapi_happy_path(self, tmp_path):
        d = tmp_path / "my_api"
        d.mkdir()
        self._write_tool(d, {
            "name": "my_api",
            "config": {"type": "openapi", "spec_file": "openapi.yaml"},
        })
        spec = {"openapi": "3.0.0", "info": {"title": "T", "version": "1"}, "paths": {}}
        (d / "openapi.yaml").write_text(yaml.dump(spec))

        defn = load_tool_def(d)
        assert defn.name == "my_api"
        assert defn.config.type == "openapi"

    def test_function_happy_path(self, tmp_path):
        d = tmp_path / "my_fn"
        d.mkdir()
        self._write_tool(d, {
            "name": "my_fn",
            "config": {"type": "function"},
        })
        (d / "logic.py").write_text("async def run(x: str) -> str: return x\n")

        defn = load_tool_def(d)
        assert defn.name == "my_fn"
        assert defn.config.type == "function"

    def test_mcp_happy_path(self, tmp_path):
        d = tmp_path / "my_mcp"
        d.mkdir()
        self._write_tool(d, {
            "name": "my_mcp",
            "config": {"type": "mcp", "server_url": "https://mcp.example.com/sse"},
        })

        defn = load_tool_def(d)
        assert defn.config.type == "mcp"

    def test_missing_tool_yaml_raises(self, tmp_path):
        d = tmp_path / "empty"
        d.mkdir()
        with pytest.raises(FileNotFoundError, match="tool.yaml not found"):
            load_tool_def(d)

    def test_non_mapping_yaml_raises(self, tmp_path):
        d = tmp_path / "bad"
        d.mkdir()
        (d / "tool.yaml").write_text("- list item\n- another")
        with pytest.raises(ValueError, match="YAML mapping"):
            load_tool_def(d)

    def test_invalid_config_raises_validation_error(self, tmp_path):
        d = tmp_path / "bad_cfg"
        d.mkdir()
        self._write_tool(d, {"name": "x", "config": {"type": "openapi", "timeout_seconds": -5}})
        (d / "openapi.yaml").write_text("{}")
        with pytest.raises(ValidationError):
            load_tool_def(d)

    def test_missing_openapi_spec_raises(self, tmp_path):
        d = tmp_path / "no_spec"
        d.mkdir()
        self._write_tool(d, {
            "name": "no_spec",
            "config": {"type": "openapi", "spec_file": "missing.yaml"},
        })
        with pytest.raises(FileNotFoundError, match="missing.yaml"):
            load_tool_def(d)

    def test_missing_logic_py_raises(self, tmp_path):
        d = tmp_path / "no_logic"
        d.mkdir()
        self._write_tool(d, {"name": "no_logic", "config": {"type": "function"}})
        with pytest.raises(FileNotFoundError, match="logic.py"):
            load_tool_def(d)

    def test_schema_files_validated_when_present(self, tmp_path):
        """Valid JSON Schema files should pass silently."""
        d = tmp_path / "with_schemas"
        d.mkdir()
        self._write_tool(d, {"name": "with_schemas", "config": {"type": "function"}})
        (d / "logic.py").write_text("async def run(x: str) -> str: return x\n")
        valid_schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {"x": {"type": "string"}},
        }
        (d / "input.yaml").write_text(yaml.dump(valid_schema))
        (d / "output.yaml").write_text(yaml.dump(valid_schema))

        defn = load_tool_def(d)
        assert defn.name == "with_schemas"

    def test_invalid_schema_file_raises(self, tmp_path):
        """A non-mapping schema file should raise ValueError."""
        d = tmp_path / "bad_schema"
        d.mkdir()
        self._write_tool(d, {
            "name": "bad_schema",
            "config": {"type": "function"},
            "input_schema": "input.yaml",
        })
        (d / "logic.py").write_text("async def run(x: str) -> str: return x\n")
        (d / "input.yaml").write_text("- not a mapping\n")
        with pytest.raises(ValueError, match="YAML mapping"):
            load_tool_def(d)

    def test_custom_spec_file_name(self, tmp_path):
        d = tmp_path / "custom_spec"
        d.mkdir()
        self._write_tool(d, {
            "name": "custom_spec",
            "config": {"type": "openapi", "spec_file": "my_api.yaml"},
        })
        spec = {"openapi": "3.0.0", "info": {"title": "T", "version": "1"}, "paths": {}}
        (d / "my_api.yaml").write_text(yaml.dump(spec))

        defn = load_tool_def(d)
        assert defn.config.spec_file == "my_api.yaml"

    def test_function_with_parameters(self, tmp_path):
        d = tmp_path / "fn_params"
        d.mkdir()
        self._write_tool(d, {
            "name": "fn_params",
            "config": {
                "type": "function",
                "parameters": {"model_version": "v3", "threshold": "0.75"},
            },
        })
        (d / "logic.py").write_text("async def run(**kw): return kw\n")
        defn = load_tool_def(d)
        assert defn.config.parameters["model_version"] == "v3"
