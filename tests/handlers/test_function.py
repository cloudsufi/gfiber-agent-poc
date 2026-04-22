"""Unit tests for agent_tools.handlers.function_handler."""
from __future__ import annotations

import pytest

from agent_tools.core.definition import ExecutionConfig, ToolDefinition
from agent_tools.core.runtime import ExecutionContext
from agent_tools.handlers.function_handler import FunctionHandler


def _make_ctx(tool_dir, validated_input=None):
    defn = ToolDefinition(
        name="function_tool",
        version="1.0",
        type="function",
        description="",
        config={"async_mode": True},
        execution=ExecutionConfig(retries=0, timeout=5),
        handler_class=FunctionHandler,
        tool_dir=tool_dir,
    )
    return ExecutionContext(
        tool_def=defn,
        raw_kwargs={},
        validated_input=validated_input or {},
    )


class TestFunctionHandler:
    @pytest.mark.asyncio
    async def test_runs_logic_py(self, sample_function_tool_dir):
        ctx = _make_ctx(sample_function_tool_dir, {"text": "hello"})
        result = await FunctionHandler().execute(ctx)
        assert result == {"output": "hello_ok"}

    @pytest.mark.asyncio
    async def test_missing_logic_py_raises(self, tmp_path):
        ctx = _make_ctx(tmp_path)
        with pytest.raises(FileNotFoundError, match="logic.py"):
            await FunctionHandler().execute(ctx)

    @pytest.mark.asyncio
    async def test_logic_missing_run_raises(self, tmp_path):
        (tmp_path / "logic.py").write_text("x = 1\n")
        ctx = _make_ctx(tmp_path)
        with pytest.raises(AttributeError, match="run"):
            await FunctionHandler().execute(ctx)

    @pytest.mark.asyncio
    async def test_no_tool_dir_raises(self):
        defn = ToolDefinition(
            name="no_dir",
            version="1.0",
            type="function",
            description="",
            config={},
            execution=ExecutionConfig(),
            handler_class=FunctionHandler,
            tool_dir=None,
        )
        ctx = ExecutionContext(tool_def=defn, raw_kwargs={})
        with pytest.raises(ValueError, match="tool_dir"):
            await FunctionHandler().execute(ctx)

    @pytest.mark.asyncio
    async def test_parameters_merged_into_inputs(self, tmp_path):
        """Static config parameters should appear in the run() inputs dict."""
        (tmp_path / "logic.py").write_text(
            "async def run(inputs):\n    return {'got': inputs.get('model_version')}\n"
        )
        defn = ToolDefinition(
            name="pt",
            version="1.0",
            type="function",
            description="",
            config={"parameters": {"model_version": "v9"}},
            execution=ExecutionConfig(retries=0, timeout=5),
            handler_class=FunctionHandler,
            tool_dir=tmp_path,
        )
        ctx = ExecutionContext(tool_def=defn, raw_kwargs={}, validated_input={})
        result = await FunctionHandler().execute(ctx)
        assert result == {"got": "v9"}
