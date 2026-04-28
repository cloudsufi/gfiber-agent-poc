"""
Shared pytest fixtures and google.adk stub modules.

Because google-adk is not installed in the test environment, we inject
lightweight stub objects into sys.modules before any adk_tools import
so all ``from google.adk…`` imports resolve to controllable fakes.

Stubs installed here:
  google.adk.tools                               — FunctionTool, RestApiTool
  google.adk.tools.openapi_tool…OpenAPIToolset   — OpenAPIToolset
  google.adk.tools.mcp_tool…MCPToolset           — MCPToolset, SseServerParams, StdioServerParams
  google.adk.tools.openapi_tool.auth.auth_helpers— token_to_scheme_credential, service_account_dict_to_scheme_credential
  google.adk.tools.tool_context                  — ToolContext
  google.adk.agents                              — LlmAgent
"""

from __future__ import annotations

import sys
import textwrap
import types
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml


# ── google.adk stub installation ──────────────────────────────────────────────

def _install_adk_stubs() -> None:
    """Inject stub modules into sys.modules so adk_tools imports don't fail."""

    # Helper: make a stub module with arbitrary attributes
    def _mod(name: str, **attrs: Any) -> types.ModuleType:
        m = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(m, k, v)
        return m

    # ── ToolContext stub ───────────────────────────────────────────────────────
    class _ToolContext:
        def __init__(self, state: dict | None = None):
            self.state = state or {}

    # ── FunctionTool stub ──────────────────────────────────────────────────────
    class _FunctionTool:
        def __init__(self, func: Any):
            self.func = func
            self.name = getattr(func, "__name__", "unknown")

    # ── RestApiTool stub ───────────────────────────────────────────────────────
    class _RestApiTool:
        def __init__(self, name: str = "rest_tool"):
            self.name = name

    # ── OpenAPIToolset stub ────────────────────────────────────────────────────
    class _OpenAPIToolset:
        def __init__(self, spec_dict: dict, auth_scheme: Any = None, auth_credential: Any = None):
            self.spec_dict = spec_dict
            self.auth_scheme = auth_scheme
            self.auth_credential = auth_credential
            # Derive fake tool names from spec paths
            paths = list((spec_dict.get("paths") or {}).keys())
            self._tools = [_RestApiTool(name=p.strip("/").replace("/", "_") or "api_tool") for p in paths] or [_RestApiTool()]

        def get_tools(self) -> list[_RestApiTool]:
            return self._tools

    # ── MCPToolset + params stubs ──────────────────────────────────────────────
    class _SseServerParams:
        def __init__(self, url: str, headers: dict | None = None):
            self.url = url
            self.headers = headers or {}

    class _StdioServerParams:
        def __init__(self, command: str, args: list | None = None, env: dict | None = None):
            self.command = command
            self.args = args or []
            self.env = env

    class _FakeMCPExitStack:
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass

    class _MCPToolset:
        @staticmethod
        async def from_server(connection_params: Any) -> tuple[list, _FakeMCPExitStack]:
            # Return two fake tools so filter tests have something to test
            class _MCPTool:
                def __init__(self, name: str): self.name = name
            tools = [_MCPTool("search_documents"), _MCPTool("get_document"), _MCPTool("list_sections")]
            return tools, _FakeMCPExitStack()

    # ── auth_helpers stubs ─────────────────────────────────────────────────────
    def _token_to_scheme_credential(scheme_type, location, name, token):
        return ({"type": scheme_type, "location": location, "name": name}, {"token": token})

    def _service_account_dict_to_scheme_credential(sa_dict, scopes):
        return ({"type": "service_account"}, {"sa_dict": sa_dict, "scopes": scopes})

    # ── Module tree ────────────────────────────────────────────────────────────
    google = _mod("google")
    google_adk = _mod("google.adk")
    google_adk_tools = _mod("google.adk.tools", FunctionTool=_FunctionTool)
    google_adk_agents = _mod("google.adk.agents", LlmAgent=MagicMock())
    google_adk_tool_context = _mod("google.adk.tools.tool_context", ToolContext=_ToolContext)

    # openapi_tool subtree
    openapi_root = _mod("google.adk.tools.openapi_tool")
    openapi_spec_parser = _mod("google.adk.tools.openapi_tool.openapi_spec_parser")
    openapi_toolset_mod = _mod(
        "google.adk.tools.openapi_tool.openapi_spec_parser.openapi_toolset",
        OpenAPIToolset=_OpenAPIToolset,
    )
    openapi_auth = _mod("google.adk.tools.openapi_tool.auth")
    openapi_auth_helpers = _mod(
        "google.adk.tools.openapi_tool.auth.auth_helpers",
        token_to_scheme_credential=_token_to_scheme_credential,
        service_account_dict_to_scheme_credential=_service_account_dict_to_scheme_credential,
    )

    # mcp_tool subtree
    mcp_root = _mod("google.adk.tools.mcp_tool")
    mcp_toolset_mod = _mod(
        "google.adk.tools.mcp_tool.mcp_toolset",
        MCPToolset=_MCPToolset,
        SseServerParams=_SseServerParams,
        StdioServerParams=_StdioServerParams,
    )

    # Register everything in sys.modules
    for name, mod in [
        ("google", google),
        ("google.adk", google_adk),
        ("google.adk.tools", google_adk_tools),
        ("google.adk.agents", google_adk_agents),
        ("google.adk.tools.tool_context", google_adk_tool_context),
        ("google.adk.tools.openapi_tool", openapi_root),
        ("google.adk.tools.openapi_tool.openapi_spec_parser", openapi_spec_parser),
        ("google.adk.tools.openapi_tool.openapi_spec_parser.openapi_toolset", openapi_toolset_mod),
        ("google.adk.tools.openapi_tool.auth", openapi_auth),
        ("google.adk.tools.openapi_tool.auth.auth_helpers", openapi_auth_helpers),
        ("google.adk.tools.mcp_tool", mcp_root),
        ("google.adk.tools.mcp_tool.mcp_toolset", mcp_toolset_mod),
    ]:
        if name not in sys.modules:
            sys.modules[name] = mod

    # Export the stub classes so tests can reference them
    sys.modules[__name__]._ToolContext = _ToolContext
    sys.modules[__name__]._FunctionTool = _FunctionTool
    sys.modules[__name__]._OpenAPIToolset = _OpenAPIToolset
    sys.modules[__name__]._MCPToolset = _MCPToolset
    sys.modules[__name__]._SseServerParams = _SseServerParams
    sys.modules[__name__]._StdioServerParams = _StdioServerParams


# Install stubs immediately at collection time (before any adk_tools import).
_install_adk_stubs()


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture()
def tool_context():
    """A minimal ToolContext-like object with a mutable state dict."""
    ctx = sys.modules["google.adk.tools.tool_context"].ToolContext(
        state={"session_id": "test-session", "user_id": "user-1"}
    )
    return ctx


@pytest.fixture()
def tmp_tools_dir(tmp_path: Path) -> Path:
    """Return a temporary ``tools/`` directory (empty)."""
    d = tmp_path / "tools"
    d.mkdir()
    return d


@pytest.fixture()
def make_openapi_tool_dir(tmp_tools_dir: Path):
    """
    Factory fixture: create a minimal OpenAPI tool directory.

    Usage::

        tool_dir = make_openapi_tool_dir("my_api", auth=None)
    """
    _minimal_spec = {
        "openapi": "3.0.0",
        "info": {"title": "Test API", "version": "1.0"},
        "paths": {
            "/test": {
                "get": {
                    "operationId": "get_test",
                    "summary": "Test endpoint",
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }

    def _factory(name: str = "test_api", *, spec: dict | None = None, auth: dict | None = None, extra_yaml: dict | None = None) -> Path:
        d = tmp_tools_dir / name
        d.mkdir()
        tool_yaml: dict = {
            "name": name,
            "version": "1.0",
            "description": f"Test tool {name}",
            "config": {"type": "openapi", "spec_file": "openapi.yaml"},
        }
        if auth:
            tool_yaml["config"]["auth"] = auth
        if extra_yaml:
            tool_yaml.update(extra_yaml)
        (d / "tool.yaml").write_text(yaml.dump(tool_yaml))
        (d / "openapi.yaml").write_text(yaml.dump(spec or _minimal_spec))
        return d

    return _factory


@pytest.fixture()
def make_function_tool_dir(tmp_tools_dir: Path):
    """
    Factory fixture: create a minimal Function tool directory.

    Usage::

        tool_dir = make_function_tool_dir("my_func", logic_src="async def run(x: str) -> str: return x")
    """
    def _factory(
        name: str = "test_func",
        *,
        logic_src: str | None = None,
        parameters: dict | None = None,
        function_name: str = "run",
    ) -> Path:
        d = tmp_tools_dir / name
        d.mkdir()
        tool_yaml: dict = {
            "name": name,
            "version": "1.0",
            "description": f"Test function tool {name}",
            "config": {"type": "function", "function": function_name},
        }
        if parameters:
            tool_yaml["config"]["parameters"] = parameters
        (d / "tool.yaml").write_text(yaml.dump(tool_yaml))

        default_logic = textwrap.dedent("""
            async def run(value: str) -> str:
                \"\"\"Echo the value.\"\"\"
                return value
        """)
        (d / "logic.py").write_text(logic_src or default_logic)
        return d

    return _factory


@pytest.fixture()
def make_mcp_tool_dir(tmp_tools_dir: Path):
    """
    Factory fixture: create a minimal MCP (SSE) tool directory.

    Usage::

        tool_dir = make_mcp_tool_dir("my_mcp", server_url="http://mcp.example.com/sse")
    """
    def _factory(
        name: str = "test_mcp",
        *,
        server_url: str = "https://mcp.example.com/sse",
        tool_filter: list[str] | None = None,
        auth: dict | None = None,
    ) -> Path:
        d = tmp_tools_dir / name
        d.mkdir()
        cfg: dict = {"type": "mcp", "server_url": server_url}
        if tool_filter:
            cfg["tool_filter"] = tool_filter
        if auth:
            cfg["auth"] = auth
        tool_yaml: dict = {
            "name": name,
            "version": "1.0",
            "description": f"Test MCP tool {name}",
            "config": cfg,
        }
        (d / "tool.yaml").write_text(yaml.dump(tool_yaml))
        return d

    return _factory
