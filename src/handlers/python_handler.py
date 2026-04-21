"""PythonHandler — executes custom Python tools via a ``logic.py`` module."""
from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING, Any

from agent_tools.handlers.base import BaseHandler

if TYPE_CHECKING:
    from agent_tools.core.runtime import ExecutionContext


class PythonHandler(BaseHandler):
    """
    Loads ``logic.py`` from the tool directory and calls ``run(input_dict)``.

    ``run()`` must be an async function::

        async def run(inputs: dict) -> dict:
            ...
    """

    async def execute(self, ctx: "ExecutionContext") -> Any:
        if ctx.tool_def.tool_dir is None:
            raise ValueError(
                f"Tool '{ctx.tool_def.name}' has no tool_dir set — cannot load logic.py"
            )

        logic_path = ctx.tool_def.tool_dir / "logic.py"
        if not logic_path.exists():
            raise FileNotFoundError(
                f"logic.py not found for tool '{ctx.tool_def.name}': {logic_path}"
            )

        spec = importlib.util.spec_from_file_location("logic", logic_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load logic.py: {logic_path}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]

        if not hasattr(module, "run"):
            raise AttributeError(
                f"logic.py for tool '{ctx.tool_def.name}' must define an async ``run(inputs)`` function."
            )

        # Merge validated input with static parameters from config
        call_input = {
            **ctx.validated_input,
            **ctx.tool_def.config.get("parameters", {}),
        }
        return await module.run(call_input)