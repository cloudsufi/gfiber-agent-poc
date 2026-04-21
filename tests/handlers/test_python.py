"""Unit tests for agent_tools.handlers.python_handler."""
from __future__ import annotations

import pytest

from agent_tools.core.definition import ExecutionConfig, ToolDefinition
from agent_tools.core.runtime import ExecutionContext
from agent_tools.handlers.python_handler import PythonHandler


def _make_ctx(tool_dir, validated_input=None):
    from agent_tools.handlers.python_handler import PythonHandler
    defn = ToolDefinition(
        name="py_tool",
        version="1.0",
        type="python",
        description="",
        config={"async_mode": True},
        execution=ExecutionConfig(retries=0, timeout=5),
        handler_class=PythonHandler,
        tool_dir=tool_dir,
    )
    return ExecutionContext(
        tool_def=defn,
        raw_kwargs={},
        validated_input=validated_input or {},
    )


class TestPythonHandler:
    @pytest.mark.asyncio
    async def test_runs_logic_py(self, sample_python_tool_dir):
        ctx = _make_ctx(sample_python_tool_dir, {"text": "hello"})
        result = await PythonHandler().execute(ctx)
        assert result == {"output": "hello_ok"}

    @pytest.mark.asyncio
    async def test_missing_logic_py_raises(self, tmp_path):
        ctx = _make_ctx(tmp_path)
        with pytest.raises(FileNotFoundError, match="logic.py"):
            await PythonHandler().execute(ctx)

    @pytest.mark.asyncio
    async def test_logic_missing_run_raises(self, tmp_path):
        (tmp_path / "logic.py").write_text("x = 1\n")
        ctx = _make_ctx(tmp_path)
        with pytest.raises(AttributeError, match="run"):
            await PythonHandler().execute(ctx)

    @pytest.mark.asyncio
    async def test_no_tool_dir_raises(self):
        from agent_tools.handlers.python_handler import PythonHandler
        defn = ToolDefinition(
            name="no_dir",
            version="1.0",
            type="python",
            description="",
            config={},
            execution=ExecutionConfig(),
            handler_class=PythonHandler,
            tool_dir=None,
        )
        ctx = ExecutionContext(tool_def=defn, raw_kwargs={})
        with pytest.raises(ValueError, match="tool_dir"):
            await PythonHandler().execute(ctx)
