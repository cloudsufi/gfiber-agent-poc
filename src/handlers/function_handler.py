"""
FunctionHandler — runs arbitrary Python logic shipped with the tool.

For a tool with ``type: function``, the handler loads a sibling ``logic.py``
file from the tool's directory, finds an
``async def run(tool_context, inputs: dict) -> dict`` function, and awaits it.

Arguments:
1. ``tool_context`` — :class:`ToolContext` with session_id, user_id, event_type, timestamp
2. ``inputs`` — merged dict of validated request fields + static ``parameters``

The ``inputs`` dict is the merge of:

1. ``ctx.validated_input`` — request fields, already type-checked
2. ``ctx.tool_def.config["parameters"]`` — static values declared in
   ``tool.yaml`` (useful for threshold constants, model versions, etc.)

In that order. If a name collides, the static ``parameters`` win — which is
the pragmatic default when a tool declares "this parameter is fixed,
ignore any user value".

Module loading uses ``importlib.util.spec_from_file_location`` so ``logic.py``
doesn't have to live on ``sys.path``. Each tool's ``logic.py`` is loaded
under the same module name (``logic``), which is fine because the handler
re-resolves the spec every call — there's no module caching between tools.

Failure modes
-------------
* ``tool_dir is None``              → :class:`ValueError` (framework bug)
* ``logic.py`` file missing         → :class:`FileNotFoundError`
* Module loads but no ``run``       → :class:`AttributeError`
* ``run`` is not async              → ``await`` will raise ``TypeError``
"""

from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING, Any

from agent_tools.handlers.base import BaseHandler

if TYPE_CHECKING:
    from agent_tools.core.runtime import ExecutionContext


class FunctionHandler(BaseHandler):
    """
    Loads ``logic.py`` from the tool directory and awaits ``run(tool_context, inputs)``.

    ``run()`` must be an async function::

        async def run(tool_context, inputs: dict) -> dict:
            # tool_context carries session_id, user_id, event_type, timestamp
            # inputs merges validated request fields with static parameters
            ...

    ``inputs`` merges the validated request fields with the static
    ``parameters`` map from ``tool.yaml``.
    """

    async def execute(self, ctx: ExecutionContext) -> Any:
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
                f"logic.py for tool '{ctx.tool_def.name}' must define an async "
                f"``run(tool_context, inputs)`` function."
            )

        call_input = {
            **ctx.validated_input,
            **ctx.tool_def.config.get("parameters", {}),
        }
        return await module.run(ctx.tool_context, call_input)
