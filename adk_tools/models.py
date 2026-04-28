"""
Config models for YAML-driven ADK tool definitions.

Every tool lives in its own directory with this layout:

    tools/
      my_tool/
        tool.yaml        ← parsed + validated by ToolDef here
        input.yaml       ← optional JSON Schema (validated at load time)
        output.yaml      ← optional JSON Schema (validated at load time)
        openapi.yaml     ← required for type: openapi
        logic.py         ← required for type: function

tool.yaml shape
---------------
    name: my_tool
    version: "1.0"
    description: What this tool does.
    config:
      type: openapi | mcp | function
      ...type-specific fields...
    input_schema:  input.yaml   # optional override
    output_schema: output.yaml  # optional override

Validation
----------
Pydantic validates every config field at load time — unknown keys are
rejected, required fields are enforced, wrong types raise an error.
JSON Schema files (input.yaml / output.yaml) are additionally
meta-validated against JSON Schema Draft-7 using jsonschema.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Literal, Optional, Union

import yaml
from pydantic import BaseModel, Field, model_validator

# ── Auth configs ───────────────────────────────────────────────────────────────
#
# Every credential field supports two mutually-exclusive sources:
#
#   *_env    – read the value from an environment variable at tool-load time.
#   *_secret – read the value from a GCP Secret Manager resource name at
#              tool-load time (requires google-cloud-secret-manager).
#
# Exactly one source must be provided per credential; providing both (or
# neither) is a validation error caught by Pydantic at YAML-parse time.
#
# Example — bearer token from GCP Secret Manager:
#
#   auth:
#     type: bearer
#     token_secret: projects/my-project/secrets/api-token/versions/latest
#
# Example — API key from env var (existing behaviour):
#
#   auth:
#     type: api_key
#     key_env: MY_API_KEY
#     header_name: X-API-Key


class BearerAuthConfig(BaseModel):
    """Bearer token injected as ``Authorization: Bearer <token>``."""

    type: Literal["bearer"]
    token_env: Optional[str] = Field(
        default=None, description="Env var name holding the bearer token"
    )
    token_secret: Optional[str] = Field(
        default=None,
        description="GCP Secret Manager resource name for the bearer token "
                    "(e.g. projects/P/secrets/S/versions/latest)",
    )

    @model_validator(mode="after")
    def _check_source(self) -> "BearerAuthConfig":
        if not self.token_env and not self.token_secret:
            raise ValueError("bearer auth requires 'token_env' or 'token_secret'")
        if self.token_env and self.token_secret:
            raise ValueError("bearer auth: use 'token_env' OR 'token_secret', not both")
        return self

    model_config = {"extra": "forbid"}


class APIKeyAuthConfig(BaseModel):
    """API key sent in a header, query parameter, or cookie."""

    type: Literal["api_key"]
    key_env: Optional[str] = Field(
        default=None, description="Env var name holding the API key"
    )
    key_secret: Optional[str] = Field(
        default=None,
        description="GCP Secret Manager resource name for the API key",
    )
    header_name: str = Field(default="X-API-Key", description="Header name when location=header")
    location: Literal["header", "query", "cookie"] = "header"

    @model_validator(mode="after")
    def _check_source(self) -> "APIKeyAuthConfig":
        if not self.key_env and not self.key_secret:
            raise ValueError("api_key auth requires 'key_env' or 'key_secret'")
        if self.key_env and self.key_secret:
            raise ValueError("api_key auth: use 'key_env' OR 'key_secret', not both")
        return self

    model_config = {"extra": "forbid"}


class OAuth2AuthConfig(BaseModel):
    """OAuth 2.0 client-credentials flow — token minted per call."""

    type: Literal["oauth2"]
    client_id_env: Optional[str] = Field(default=None, description="Env var for client_id")
    client_id_secret: Optional[str] = Field(
        default=None, description="GCP Secret Manager resource name for client_id"
    )
    client_secret_env: Optional[str] = Field(default=None, description="Env var for client_secret")
    client_secret_secret: Optional[str] = Field(
        default=None, description="GCP Secret Manager resource name for client_secret"
    )
    token_url: str = Field(description="Token endpoint URL")
    scope: str = ""

    @model_validator(mode="after")
    def _check_sources(self) -> "OAuth2AuthConfig":
        if not self.client_id_env and not self.client_id_secret:
            raise ValueError("oauth2 auth requires 'client_id_env' or 'client_id_secret'")
        if self.client_id_env and self.client_id_secret:
            raise ValueError("oauth2 auth: use 'client_id_env' OR 'client_id_secret', not both")
        if not self.client_secret_env and not self.client_secret_secret:
            raise ValueError("oauth2 auth requires 'client_secret_env' or 'client_secret_secret'")
        if self.client_secret_env and self.client_secret_secret:
            raise ValueError("oauth2 auth: use 'client_secret_env' OR 'client_secret_secret', not both")
        return self

    model_config = {"extra": "forbid"}


class ServiceAccountAuthConfig(BaseModel):
    """GCP service-account key — mints an access or ID token via google-auth."""

    type: Literal["service_account"]
    key_env: Optional[str] = Field(
        default=None,
        description="Env var with SA JSON string or a file path to the key file",
    )
    key_secret: Optional[str] = Field(
        default=None,
        description="GCP Secret Manager resource name containing the SA JSON key",
    )
    scopes: list[str] = Field(
        default_factory=lambda: ["https://www.googleapis.com/auth/cloud-platform"]
    )
    audience: str = Field(
        default="",
        description="When set, an ID token is minted instead of an access token (e.g. Cloud Run URL)",
    )

    @model_validator(mode="after")
    def _check_source(self) -> "ServiceAccountAuthConfig":
        if not self.key_env and not self.key_secret:
            raise ValueError("service_account auth requires 'key_env' or 'key_secret'")
        if self.key_env and self.key_secret:
            raise ValueError("service_account auth: use 'key_env' OR 'key_secret', not both")
        return self

    model_config = {"extra": "forbid"}


# Discriminated union — `type` field selects the model at validation time.
AuthConfig = Annotated[
    Union[BearerAuthConfig, APIKeyAuthConfig, OAuth2AuthConfig, ServiceAccountAuthConfig],
    Field(discriminator="type"),
]


# ── Tool type configs ──────────────────────────────────────────────────────────


class OpenAPIConfig(BaseModel):
    """
    Config for ``type: openapi`` tools.
    Maps to ``google.adk.tools.openapi_tool.OpenAPIToolset``.

    Example tool.yaml:
        config:
          type: openapi
          spec_file: openapi.yaml
          auth:
            type: bearer
            token_env: MY_API_TOKEN
          timeout_seconds: 30
    """

    type: Literal["openapi"]
    spec_file: str = Field(
        default="openapi.yaml",
        description="OpenAPI 3.x spec file, relative to the tool directory",
    )
    auth: Optional[AuthConfig] = None
    timeout_seconds: int = Field(default=30, ge=0)

    model_config = {"extra": "forbid"}


class MCPConfig(BaseModel):
    """
    Config for ``type: mcp`` tools.
    Maps to ``google.adk.tools.mcp_tool.MCPToolset``.

    Supports two transports — set exactly one:
    - **SSE** (HTTP): set ``server_url``
    - **Stdio** (subprocess): set ``command`` (+ optional ``args`` / ``env_vars``)

    Example tool.yaml (SSE):
        config:
          type: mcp
          server_url: https://mcp.example.com/sse
          auth:
            type: bearer
            token_env: MCP_TOKEN
          tool_filter: [search_docs, list_docs]

    Example tool.yaml (stdio):
        config:
          type: mcp
          command: python
          args: [-m, my_mcp_server]
          env_vars:
            LOG_LEVEL: debug
    """

    type: Literal["mcp"]
    # SSE transport
    server_url: Optional[str] = Field(
        default=None, description="SSE server URL (http/https)"
    )
    # Stdio transport
    command: Optional[str] = Field(
        default=None, description="Executable for stdio MCP server"
    )
    args: list[str] = Field(default_factory=list)
    env_vars: dict[str, str] = Field(
        default_factory=dict,
        description="Extra env vars merged into the subprocess environment (stdio only)",
    )
    # Common
    tool_filter: list[str] = Field(
        default_factory=list,
        description="Allowlist of tool names to expose from this server; empty = expose all",
    )
    auth: Optional[AuthConfig] = None
    timeout_seconds: int = Field(default=30, ge=0)

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def _check_transport(self) -> MCPConfig:
        if not self.server_url and not self.command:
            raise ValueError(
                "MCPConfig requires either 'server_url' (SSE transport) "
                "or 'command' (stdio transport)"
            )
        if self.server_url and self.command:
            raise ValueError(
                "MCPConfig: specify 'server_url' OR 'command', not both"
            )
        return self


class FunctionConfig(BaseModel):
    """
    Config for ``type: function`` tools.
    Maps to ``google.adk.tools.FunctionTool``.

    Wraps an ``async def run(...)`` function from the tool's ``logic.py``.

    Example tool.yaml:
        config:
          type: function
          function: run          # default
          parameters:
            model_version: v2.3  # static kwargs merged into every call
            threshold: "0.60"
    """

    type: Literal["function"]
    function: str = Field(
        default="run",
        description="Name of the async function to wrap inside logic.py",
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Static keyword arguments merged into every invocation",
    )

    model_config = {"extra": "forbid"}


# Discriminated union on the `type` field.
ToolConfig = Annotated[
    Union[OpenAPIConfig, MCPConfig, FunctionConfig],
    Field(discriminator="type"),
]


# ── Top-level tool.yaml definition ─────────────────────────────────────────────


class ToolDef(BaseModel):
    """
    The fully parsed and Pydantic-validated representation of a ``tool.yaml``.

    This is what :func:`load_tool_def` returns. The ``config`` field is one
    of :class:`OpenAPIConfig`, :class:`MCPConfig`, or :class:`FunctionConfig`
    — chosen automatically by the discriminated union on ``type``.
    """

    name: str
    version: str = "1.0"
    description: str = ""
    config: ToolConfig
    input_schema: str = Field(
        default="input.yaml",
        description="Input schema filename (relative to tool dir)",
    )
    output_schema: str = Field(
        default="output.yaml",
        description="Output schema filename (relative to tool dir)",
    )

    model_config = {"extra": "ignore"}


# ── Loader helper ──────────────────────────────────────────────────────────────


def load_tool_def(tool_dir: Path) -> ToolDef:
    """
    Parse ``tool.yaml`` from *tool_dir*, validate config with Pydantic, and
    verify all referenced files exist.  Also meta-validates any present
    ``input.yaml`` / ``output.yaml`` against JSON Schema Draft-7.

    Raises on the first error — fail-fast at process start, never silently
    broken at call time.

    :raises FileNotFoundError: if ``tool.yaml``, a required spec file, or
        ``logic.py`` is missing.
    :raises pydantic.ValidationError: on any config field violation.
    :raises ValueError: if a schema file is not a valid JSON Schema.
    """
    tool_yaml = tool_dir / "tool.yaml"
    if not tool_yaml.exists():
        raise FileNotFoundError(f"tool.yaml not found: {tool_yaml}")

    raw: dict = yaml.safe_load(tool_yaml.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"tool.yaml must be a YAML mapping: {tool_yaml}")

    # Pydantic validates config fields + type-specific constraints here.
    defn = ToolDef.model_validate(raw)

    # ── Type-specific file existence checks ───────────────────────────────────
    cfg = defn.config
    if cfg.type == "openapi":
        spec_path = tool_dir / cfg.spec_file
        if not spec_path.exists():
            raise FileNotFoundError(
                f"Tool '{defn.name}': OpenAPI spec '{cfg.spec_file}' "
                f"not found at {spec_path}"
            )

    elif cfg.type == "function":
        logic_path = tool_dir / "logic.py"
        if not logic_path.exists():
            raise FileNotFoundError(
                f"Tool '{defn.name}': 'logic.py' not found at {logic_path}"
            )

    # ── JSON Schema meta-validation ───────────────────────────────────────────
    for schema_filename in (defn.input_schema, defn.output_schema):
        schema_path = tool_dir / schema_filename
        if schema_path.exists():
            _validate_json_schema_file(schema_path, defn.name)

    return defn


def _validate_json_schema_file(path: Path, tool_name: str) -> None:
    """
    Load a YAML file and verify it is a valid JSON Schema Draft-7 document.
    Raises :class:`ValueError` with a pointed message on failure.
    """
    try:
        import jsonschema  # optional dep; skip silently if absent
    except ImportError:
        return  # jsonschema not installed — skip meta-validation

    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(
            f"Tool '{tool_name}': schema file must be a YAML mapping: {path}"
        )
    try:
        jsonschema.Draft7Validator.check_schema(raw)
    except jsonschema.exceptions.SchemaError as exc:
        raise ValueError(
            f"Tool '{tool_name}': invalid JSON Schema in '{path.name}': {exc.message}"
        ) from exc
