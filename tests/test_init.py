"""
Tests for adk_tools/__init__.py public API.

Covers:
- discover_tools() / all_tools alias — returns combined list
- function_tool decorator — wraps function and registers it
- registered_tools() — returns copy of registry
- load_tools() — explicit sync loader
- load_tools_async() — explicit async loader
- TOOLS_DIR — resolved path
- globals injection — tools accessible by name
- _resolve_dir helper — fallback logic
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path
from contextlib import AsyncExitStack

import pytest
import yaml


# ── discover_tools / all_tools ─────────────────────────────────────────────────

class TestDiscoverTools:
    def test_returns_list(self):
        import adk_tools
        tools = adk_tools.discover_tools()
        assert isinstance(tools, list)

    def test_all_tools_is_alias(self):
        import adk_tools
        assert adk_tools.all_tools is adk_tools.discover_tools

    def test_all_tools_returns_same_result(self):
        import adk_tools
        assert adk_tools.all_tools() == adk_tools.discover_tools()

    def test_no_duplicates(self):
        import adk_tools
        tools = adk_tools.discover_tools()
        ids = [id(t) for t in tools]
        assert len(ids) == len(set(ids)), "discover_tools returned duplicate tool objects"

    def test_includes_registered_tools(self):
        import adk_tools
        # Clear registry first to isolate this test
        original_registry = list(adk_tools._FUNCTION_REGISTRY)
        adk_tools._FUNCTION_REGISTRY.clear()

        async def my_test_fn(x: str) -> str:
            """Test fn."""
            return x

        adk_tools.function_tool(my_test_fn)
        tools = adk_tools.discover_tools()
        assert len(tools) >= 1

        # Restore
        adk_tools._FUNCTION_REGISTRY.clear()
        adk_tools._FUNCTION_REGISTRY.extend(original_registry)


# ── function_tool decorator ────────────────────────────────────────────────────

class TestFunctionToolDecorator:
    def setup_method(self):
        """Save and clear registry before each test."""
        import adk_tools
        self._saved = list(adk_tools._FUNCTION_REGISTRY)
        adk_tools._FUNCTION_REGISTRY.clear()

    def teardown_method(self):
        """Restore registry after each test."""
        import adk_tools
        adk_tools._FUNCTION_REGISTRY.clear()
        adk_tools._FUNCTION_REGISTRY.extend(self._saved)

    def test_decorator_registers_tool(self):
        import adk_tools

        @adk_tools.function_tool
        async def greet(name: str) -> str:
            """Greet a user."""
            return f"Hello {name}"

        assert greet in adk_tools._FUNCTION_REGISTRY

    def test_decorated_tool_has_func_attribute(self):
        import adk_tools

        @adk_tools.function_tool
        async def ping() -> str:
            """Ping."""
            return "pong"

        # Our FunctionTool stub exposes .func
        assert hasattr(ping, "func") or callable(ping)

    def test_multiple_decorations(self):
        import adk_tools

        @adk_tools.function_tool
        async def fn_a(x: str) -> str: return x

        @adk_tools.function_tool
        async def fn_b(y: int) -> int: return y

        assert len(adk_tools._FUNCTION_REGISTRY) == 2

    def test_decorated_tools_in_discover(self):
        import adk_tools

        @adk_tools.function_tool
        async def helper_fn(data: str) -> str:
            """Helper."""
            return data

        tools = adk_tools.discover_tools()
        assert helper_fn in tools


# ── registered_tools ──────────────────────────────────────────────────────────

class TestRegisteredTools:
    def setup_method(self):
        import adk_tools
        self._saved = list(adk_tools._FUNCTION_REGISTRY)
        adk_tools._FUNCTION_REGISTRY.clear()

    def teardown_method(self):
        import adk_tools
        adk_tools._FUNCTION_REGISTRY.clear()
        adk_tools._FUNCTION_REGISTRY.extend(self._saved)

    def test_returns_list(self):
        import adk_tools
        assert isinstance(adk_tools.registered_tools(), list)

    def test_returns_copy(self):
        import adk_tools

        @adk_tools.function_tool
        async def fn(x: str) -> str: return x

        reg = adk_tools.registered_tools()
        reg.clear()
        # Original registry should be unaffected
        assert len(adk_tools._FUNCTION_REGISTRY) == 1

    def test_empty_when_no_decorators(self):
        import adk_tools
        assert adk_tools.registered_tools() == []


# ── load_tools (explicit sync) ─────────────────────────────────────────────────

class TestLoadTools:
    def test_loads_from_explicit_dir(self, tmp_path):
        import adk_tools
        # Create a minimal function tool dir
        d = tmp_path / "tools" / "simple_fn"
        d.mkdir(parents=True)
        (d / "tool.yaml").write_text(yaml.dump({
            "name": "simple_fn",
            "config": {"type": "function"},
        }))
        (d / "logic.py").write_text("async def run(x: str) -> str: return x\n")

        tools = adk_tools.load_tools(tmp_path / "tools", include_registered=False)
        assert len(tools) == 1

    def test_include_registered_true(self, tmp_path):
        import adk_tools
        original = list(adk_tools._FUNCTION_REGISTRY)
        adk_tools._FUNCTION_REGISTRY.clear()

        @adk_tools.function_tool
        async def reg_fn(x: str) -> str: return x

        d = tmp_path / "tools2"
        d.mkdir()
        # empty dir — no tool.yaml dirs
        tools = adk_tools.load_tools(d, include_registered=True)
        assert reg_fn in tools

        adk_tools._FUNCTION_REGISTRY.clear()
        adk_tools._FUNCTION_REGISTRY.extend(original)

    def test_include_registered_false_excludes_registry(self, tmp_path):
        import adk_tools
        original = list(adk_tools._FUNCTION_REGISTRY)

        @adk_tools.function_tool
        async def another_fn(x: str) -> str: return x

        d = tmp_path / "tools3"
        d.mkdir()
        tools = adk_tools.load_tools(d, include_registered=False)
        assert another_fn not in tools

        adk_tools._FUNCTION_REGISTRY.clear()
        adk_tools._FUNCTION_REGISTRY.extend(original)

    def test_no_dir_no_tools_dir_raises(self, monkeypatch):
        import adk_tools
        original_tools_dir = adk_tools.TOOLS_DIR
        adk_tools.TOOLS_DIR = None
        try:
            with pytest.raises(FileNotFoundError, match="No tools directory"):
                adk_tools.load_tools()
        finally:
            adk_tools.TOOLS_DIR = original_tools_dir


# ── load_tools_async ──────────────────────────────────────────────────────────

class TestLoadToolsAsync:
    @pytest.mark.asyncio
    async def test_loads_async_from_explicit_dir(self, tmp_path):
        import adk_tools
        d = tmp_path / "tools_async" / "async_fn"
        d.mkdir(parents=True)
        (d / "tool.yaml").write_text(yaml.dump({
            "name": "async_fn",
            "config": {"type": "function"},
        }))
        (d / "logic.py").write_text("async def run(x: str) -> str: return x\n")

        tools, exit_stack = await adk_tools.load_tools_async(
            tmp_path / "tools_async", include_registered=False
        )
        assert len(tools) == 1
        assert isinstance(exit_stack, AsyncExitStack)
        await exit_stack.aclose()

    @pytest.mark.asyncio
    async def test_returns_exit_stack_type(self, tmp_path):
        import adk_tools
        d = tmp_path / "tools_exit"
        d.mkdir()
        tools, exit_stack = await adk_tools.load_tools_async(d, include_registered=False)
        assert isinstance(exit_stack, AsyncExitStack)
        await exit_stack.aclose()

    @pytest.mark.asyncio
    async def test_include_registered(self, tmp_path):
        import adk_tools
        original = list(adk_tools._FUNCTION_REGISTRY)
        adk_tools._FUNCTION_REGISTRY.clear()

        @adk_tools.function_tool
        async def async_reg_fn(x: str) -> str: return x

        d = tmp_path / "tools_areg"
        d.mkdir()
        tools, exit_stack = await adk_tools.load_tools_async(d, include_registered=True)
        assert async_reg_fn in tools
        await exit_stack.aclose()

        adk_tools._FUNCTION_REGISTRY.clear()
        adk_tools._FUNCTION_REGISTRY.extend(original)


# ── globals injection (name imports) ──────────────────────────────────────────

class TestGlobalsInjection:
    def test_tools_dir_attribute(self):
        import adk_tools
        # TOOLS_DIR is None if the default ./tools dir doesn't exist; that's OK
        assert hasattr(adk_tools, "TOOLS_DIR")

    def test_auto_loaded_tools_in_all(self):
        """__all__ must include discover_tools, all_tools, function_tool, etc."""
        import adk_tools
        for name in ("discover_tools", "all_tools", "function_tool", "registered_tools",
                     "load_tools", "load_tools_async", "ToolLoader", "TOOLS_DIR"):
            assert name in adk_tools.__all__, f"'{name}' missing from __all__"


# ── _resolve_dir helper ────────────────────────────────────────────────────────

class TestResolveDir:
    def test_explicit_path_used(self, tmp_path):
        from adk_tools import _resolve_dir
        assert _resolve_dir(tmp_path) == tmp_path

    def test_explicit_string_converted(self, tmp_path):
        from adk_tools import _resolve_dir
        result = _resolve_dir(str(tmp_path))
        assert result == tmp_path

    def test_falls_back_to_tools_dir(self, tmp_path):
        import adk_tools
        from adk_tools import _resolve_dir
        original = adk_tools.TOOLS_DIR
        adk_tools.TOOLS_DIR = tmp_path
        try:
            assert _resolve_dir(None) == tmp_path
        finally:
            adk_tools.TOOLS_DIR = original

    def test_raises_when_no_dir(self):
        import adk_tools
        from adk_tools import _resolve_dir
        original = adk_tools.TOOLS_DIR
        adk_tools.TOOLS_DIR = None
        try:
            with pytest.raises(FileNotFoundError):
                _resolve_dir(None)
        finally:
            adk_tools.TOOLS_DIR = original
