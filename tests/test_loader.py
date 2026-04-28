"""
Tests for adk_tools/loader.py

Covers:
- _wrap_with_static_params: signature grafting, tool_context, no-static-params, annotations
- ToolLoader._iter_tool_dirs: happy path, missing dir, empty dir
- ToolLoader.load_sync: openapi tool, function tool, mcp skipped with warning
- ToolLoader.load_async: all three types including MCP
- ToolLoader._build_openapi: spec loaded, auth applied
- ToolLoader._build_function: logic.py loaded, static params applied, tool_context preserved
- ToolLoader._build_mcp: SSE, stdio, tool_filter
"""

from __future__ import annotations

import inspect
import sys
import textwrap
import warnings
from contextlib import AsyncExitStack
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from adk_tools.loader import ToolLoader, _wrap_with_static_params


# ── _wrap_with_static_params ───────────────────────────────────────────────────

class TestWrapWithStaticParams:
    @pytest.mark.asyncio
    async def test_static_params_hidden_from_signature(self):
        async def original(city: str, units: str = "metric") -> dict:
            """Get weather."""
            return {"city": city, "units": units}

        wrapped = _wrap_with_static_params(
            original, static={"units": "imperial"}, name="get_weather", doc="Weather tool"
        )

        sig = inspect.signature(wrapped)
        # 'units' should be hidden from the visible signature
        assert "units" not in sig.parameters
        assert "city" in sig.parameters

    @pytest.mark.asyncio
    async def test_static_values_injected_at_call_time(self):
        received = {}

        async def original(city: str, units: str = "metric") -> dict:
            received["city"] = city
            received["units"] = units
            return received

        wrapped = _wrap_with_static_params(
            original, static={"units": "fahrenheit"}, name="w", doc=""
        )
        await wrapped(city="London")
        assert received["units"] == "fahrenheit"
        assert received["city"] == "London"

    @pytest.mark.asyncio
    async def test_tool_context_preserved_in_signature(self):
        from google.adk.tools.tool_context import ToolContext

        async def original(name: str, tool_context: ToolContext, model: str = "v1") -> str:
            return name

        wrapped = _wrap_with_static_params(
            original, static={"model": "v2"}, name="fn", doc=""
        )
        sig = inspect.signature(wrapped)
        assert "tool_context" in sig.parameters
        assert "model" not in sig.parameters
        assert "name" in sig.parameters

    @pytest.mark.asyncio
    async def test_tool_context_injected_at_call_time(self):
        from google.adk.tools.tool_context import ToolContext

        received = {}

        async def original(name: str, tool_context: ToolContext, model: str = "v1") -> str:
            received["tool_context"] = tool_context
            received["model"] = model
            return name

        ctx = ToolContext(state={"sid": "123"})
        wrapped = _wrap_with_static_params(
            original, static={"model": "v2"}, name="fn", doc=""
        )
        await wrapped(name="Alice", tool_context=ctx)
        assert received["tool_context"] is ctx
        assert received["model"] == "v2"

    @pytest.mark.asyncio
    async def test_no_static_params_signature_unchanged(self):
        async def original(x: str, y: int = 0) -> str:
            return x

        wrapped = _wrap_with_static_params(original, static={}, name="fn", doc="")
        sig = inspect.signature(wrapped)
        assert "x" in sig.parameters
        assert "y" in sig.parameters

    def test_dunder_name_and_doc_set(self):
        async def original(x: str) -> str:
            """Original doc"""
            return x

        wrapped = _wrap_with_static_params(
            original, static={}, name="custom_name", doc="Custom doc"
        )
        assert wrapped.__name__ == "custom_name"
        assert wrapped.__doc__ == "Custom doc"

    def test_annotations_mirror_visible_params(self):
        async def original(a: str, b: int, c: float = 1.0) -> str:
            return a

        wrapped = _wrap_with_static_params(original, static={"c": 2.0}, name="fn", doc="")
        assert "a" in wrapped.__annotations__
        assert "b" in wrapped.__annotations__
        assert "c" not in wrapped.__annotations__
        assert wrapped.__annotations__.get("return") is str


# ── ToolLoader._iter_tool_dirs ─────────────────────────────────────────────────

class TestIterToolDirs:
    def test_returns_sorted_dirs_with_tool_yaml(self, tmp_tools_dir):
        (tmp_tools_dir / "b_tool").mkdir()
        (tmp_tools_dir / "b_tool" / "tool.yaml").write_text("name: b")
        (tmp_tools_dir / "a_tool").mkdir()
        (tmp_tools_dir / "a_tool" / "tool.yaml").write_text("name: a")
        # Extra dir without tool.yaml — should be ignored
        (tmp_tools_dir / "no_yaml_dir").mkdir()

        dirs = ToolLoader._iter_tool_dirs(tmp_tools_dir)
        names = [d.name for d in dirs]
        assert names == sorted(names)
        assert "no_yaml_dir" not in names
        assert "a_tool" in names and "b_tool" in names

    def test_missing_tools_dir_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="tools_dir not found"):
            ToolLoader._iter_tool_dirs(tmp_path / "nonexistent")

    def test_empty_dir_returns_empty_list(self, tmp_tools_dir):
        assert ToolLoader._iter_tool_dirs(tmp_tools_dir) == []


# ── ToolLoader.load_sync ───────────────────────────────────────────────────────

class TestLoadSync:
    def test_openapi_tool_loaded(self, make_openapi_tool_dir, tmp_tools_dir):
        make_openapi_tool_dir("weather_api")
        loader = ToolLoader()
        tools = loader.load_sync(tmp_tools_dir)
        assert len(tools) >= 1

    def test_function_tool_loaded(self, make_function_tool_dir, tmp_tools_dir):
        make_function_tool_dir("score_fn")
        loader = ToolLoader()
        tools = loader.load_sync(tmp_tools_dir)
        assert len(tools) == 1
        # FunctionTool stub has a .func attribute
        assert hasattr(tools[0], "func") or hasattr(tools[0], "name")

    def test_mcp_tool_skipped_with_warning(self, make_mcp_tool_dir, tmp_tools_dir):
        make_mcp_tool_dir("docs_mcp")
        loader = ToolLoader()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            tools = loader.load_sync(tmp_tools_dir)
        assert tools == []
        assert any("mcp" in str(warning.message).lower() or "async" in str(warning.message).lower()
                   for warning in w)

    def test_multiple_tools_loaded(self, make_function_tool_dir, make_openapi_tool_dir, tmp_tools_dir):
        make_function_tool_dir("fn_tool")
        make_openapi_tool_dir("api_tool")
        loader = ToolLoader()
        tools = loader.load_sync(tmp_tools_dir)
        assert len(tools) >= 2

    def test_missing_dir_raises(self, tmp_path):
        loader = ToolLoader()
        with pytest.raises(FileNotFoundError):
            loader.load_sync(tmp_path / "nonexistent")

    def test_broken_tool_yaml_raises(self, tmp_tools_dir):
        d = tmp_tools_dir / "broken"
        d.mkdir()
        (d / "tool.yaml").write_text("- not a mapping\n")
        loader = ToolLoader()
        with pytest.raises(ValueError):
            loader.load_sync(tmp_tools_dir)


# ── ToolLoader.load_async ──────────────────────────────────────────────────────

class TestLoadAsync:
    @pytest.mark.asyncio
    async def test_function_tool_async(self, make_function_tool_dir, tmp_tools_dir):
        make_function_tool_dir("fn_async")
        loader = ToolLoader()
        tools, exit_stack = await loader.load_async(tmp_tools_dir)
        assert len(tools) == 1
        await exit_stack.aclose()

    @pytest.mark.asyncio
    async def test_openapi_tool_async(self, make_openapi_tool_dir, tmp_tools_dir):
        make_openapi_tool_dir("api_async")
        loader = ToolLoader()
        tools, exit_stack = await loader.load_async(tmp_tools_dir)
        assert len(tools) >= 1
        await exit_stack.aclose()

    @pytest.mark.asyncio
    async def test_mcp_tool_async_loaded(self, make_mcp_tool_dir, tmp_tools_dir):
        make_mcp_tool_dir("mcp_async", server_url="https://mcp.example.com/sse")
        loader = ToolLoader()
        tools, exit_stack = await loader.load_async(tmp_tools_dir)
        # Stub returns 3 MCP tools
        assert len(tools) == 3
        await exit_stack.aclose()

    @pytest.mark.asyncio
    async def test_mcp_tool_filter_applied(self, make_mcp_tool_dir, tmp_tools_dir):
        make_mcp_tool_dir(
            "mcp_filtered",
            server_url="https://mcp.example.com/sse",
            tool_filter=["search_documents"],
        )
        loader = ToolLoader()
        tools, exit_stack = await loader.load_async(tmp_tools_dir)
        assert len(tools) == 1
        assert tools[0].name == "search_documents"
        await exit_stack.aclose()

    @pytest.mark.asyncio
    async def test_returns_exit_stack(self, make_function_tool_dir, tmp_tools_dir):
        make_function_tool_dir("fn_stack")
        loader = ToolLoader()
        tools, exit_stack = await loader.load_async(tmp_tools_dir)
        assert isinstance(exit_stack, AsyncExitStack)
        await exit_stack.aclose()

    @pytest.mark.asyncio
    async def test_all_types_together(
        self, make_function_tool_dir, make_openapi_tool_dir, make_mcp_tool_dir, tmp_tools_dir
    ):
        make_function_tool_dir("fn")
        make_openapi_tool_dir("api")
        make_mcp_tool_dir("mcp")
        loader = ToolLoader()
        tools, exit_stack = await loader.load_async(tmp_tools_dir)
        # 1 function + 1+ openapi + 3 mcp
        assert len(tools) >= 5
        await exit_stack.aclose()


# ── ToolLoader._build_openapi ──────────────────────────────────────────────────

class TestBuildOpenapi:
    def test_spec_loaded_and_tools_returned(self, make_openapi_tool_dir, tmp_tools_dir):
        make_openapi_tool_dir("api_test")
        loader = ToolLoader()
        tools = loader.load_sync(tmp_tools_dir)
        assert len(tools) >= 1

    def test_with_bearer_auth(self, make_openapi_tool_dir, tmp_tools_dir, monkeypatch):
        monkeypatch.setenv("API_TOKEN", "tok123")
        make_openapi_tool_dir("api_auth", auth={"type": "bearer", "token_env": "API_TOKEN"})
        loader = ToolLoader()
        tools = loader.load_sync(tmp_tools_dir)
        assert len(tools) >= 1

    def test_missing_google_adk_raises(self, make_openapi_tool_dir, tmp_tools_dir):
        make_openapi_tool_dir("api_no_adk")
        loader = ToolLoader()
        # Temporarily remove the OpenAPIToolset from stubs
        openapi_mod = sys.modules.get("google.adk.tools.openapi_tool.openapi_spec_parser.openapi_toolset")
        original_toolset = getattr(openapi_mod, "OpenAPIToolset", None)
        try:
            delattr(openapi_mod, "OpenAPIToolset")
            with pytest.raises((ImportError, AttributeError)):
                loader.load_sync(tmp_tools_dir)
        finally:
            if original_toolset is not None:
                setattr(openapi_mod, "OpenAPIToolset", original_toolset)


# ── ToolLoader._build_function ─────────────────────────────────────────────────

class TestBuildFunction:
    def test_simple_function(self, make_function_tool_dir, tmp_tools_dir):
        logic = textwrap.dedent("""
            async def run(value: str) -> str:
                \"\"\"Return the value.\"\"\"
                return value
        """)
        make_function_tool_dir("simple", logic_src=logic)
        loader = ToolLoader()
        tools = loader.load_sync(tmp_tools_dir)
        assert len(tools) == 1

    def test_static_params_applied(self, make_function_tool_dir, tmp_tools_dir):
        logic = textwrap.dedent("""
            async def run(city: str, units: str = "metric") -> str:
                \"\"\"Get weather.\"\"\"
                return f"{city}-{units}"
        """)
        make_function_tool_dir("weather", logic_src=logic, parameters={"units": "imperial"})
        loader = ToolLoader()
        tools = loader.load_sync(tmp_tools_dir)
        tool = tools[0]
        sig = inspect.signature(tool.func)
        assert "units" not in sig.parameters
        assert "city" in sig.parameters

    def test_custom_function_name(self, make_function_tool_dir, tmp_tools_dir):
        logic = textwrap.dedent("""
            async def handler(x: str) -> str:
                return x
        """)
        make_function_tool_dir("fn_custom", logic_src=logic, function_name="handler")
        loader = ToolLoader()
        tools = loader.load_sync(tmp_tools_dir)
        assert len(tools) == 1

    def test_function_not_found_raises(self, make_function_tool_dir, tmp_tools_dir):
        logic = "async def run(x: str) -> str: return x\n"
        make_function_tool_dir("fn_missing", logic_src=logic, function_name="nonexistent")
        loader = ToolLoader()
        with pytest.raises(AttributeError, match="nonexistent"):
            loader.load_sync(tmp_tools_dir)

    def test_tool_context_in_signature(self, make_function_tool_dir, tmp_tools_dir):
        logic = textwrap.dedent("""
            try:
                from google.adk.tools.tool_context import ToolContext
            except ImportError:
                ToolContext = object

            async def run(name: str, tool_context: ToolContext, model: str = "v1") -> str:
                return name
        """)
        make_function_tool_dir("fn_ctx", logic_src=logic, parameters={"model": "v2"})
        loader = ToolLoader()
        tools = loader.load_sync(tmp_tools_dir)
        tool = tools[0]
        sig = inspect.signature(tool.func)
        assert "tool_context" in sig.parameters
        assert "model" not in sig.parameters

    @pytest.mark.asyncio
    async def test_function_callable(self, make_function_tool_dir, tmp_tools_dir):
        logic = textwrap.dedent("""
            async def run(x: str) -> str:
                \"\"\"Echo x.\"\"\"
                return f"echo:{x}"
        """)
        make_function_tool_dir("fn_call", logic_src=logic)
        loader = ToolLoader()
        tools = loader.load_sync(tmp_tools_dir)
        result = await tools[0].func(x="hello")
        assert result == "echo:hello"


# ── ToolLoader._build_mcp (SSE + stdio) ───────────────────────────────────────

class TestBuildMcp:
    @pytest.mark.asyncio
    async def test_sse_transport(self, make_mcp_tool_dir, tmp_tools_dir):
        make_mcp_tool_dir("mcp_sse", server_url="https://mcp.example.com/sse")
        loader = ToolLoader()
        tools, exit_stack = await loader.load_async(tmp_tools_dir)
        assert len(tools) == 3  # stub returns 3
        await exit_stack.aclose()

    @pytest.mark.asyncio
    async def test_stdio_transport(self, tmp_tools_dir):
        d = tmp_tools_dir / "mcp_stdio"
        d.mkdir()
        (d / "tool.yaml").write_text(yaml.dump({
            "name": "mcp_stdio",
            "config": {"type": "mcp", "command": "python", "args": ["-m", "mcp_server"]},
        }))
        loader = ToolLoader()
        tools, exit_stack = await loader.load_async(tmp_tools_dir)
        assert len(tools) == 3
        await exit_stack.aclose()

    @pytest.mark.asyncio
    async def test_tool_filter_two_tools(self, make_mcp_tool_dir, tmp_tools_dir):
        make_mcp_tool_dir(
            "mcp_filter2",
            server_url="https://mcp.example.com/sse",
            tool_filter=["search_documents", "get_document"],
        )
        loader = ToolLoader()
        tools, exit_stack = await loader.load_async(tmp_tools_dir)
        assert len(tools) == 2
        tool_names = {t.name for t in tools}
        assert tool_names == {"search_documents", "get_document"}
        await exit_stack.aclose()

    @pytest.mark.asyncio
    async def test_empty_tool_filter_returns_all(self, make_mcp_tool_dir, tmp_tools_dir):
        make_mcp_tool_dir("mcp_all", server_url="https://mcp.example.com/sse", tool_filter=[])
        loader = ToolLoader()
        tools, exit_stack = await loader.load_async(tmp_tools_dir)
        assert len(tools) == 3  # all returned by stub
        await exit_stack.aclose()

    @pytest.mark.asyncio
    async def test_mcp_with_bearer_auth(self, make_mcp_tool_dir, tmp_tools_dir, monkeypatch):
        monkeypatch.setenv("MCP_TOKEN", "tok")
        make_mcp_tool_dir(
            "mcp_auth",
            server_url="https://mcp.example.com/sse",
            auth={"type": "bearer", "token_env": "MCP_TOKEN"},
        )
        loader = ToolLoader()
        tools, exit_stack = await loader.load_async(tmp_tools_dir)
        assert len(tools) == 3
        await exit_stack.aclose()
