"""RESTHandler — executes operations described by an OpenAPI specification."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agent_tools.handlers.api_handler import APIHandler, _inject_auth_headers
from agent_tools.handlers.base import BaseHandler

if TYPE_CHECKING:
    from agent_tools.core.runtime import ExecutionContext


class RESTHandler(BaseHandler):
    """
    Drives an HTTP call from an OpenAPI spec + ``operation_id``.

    Falls back to the :class:`~agent_tools.handlers.api_handler.APIHandler`
    logic after resolving the operation's URL and method from the spec.
    """

    def __init__(self) -> None:
        self._api_handler = APIHandler()
        self._spec_cache: dict[str, Any] = {}

    async def execute(self, ctx: "ExecutionContext") -> Any:
        cfg = ctx.tool_def.config
        spec = await self._load_spec(cfg)
        operation = self._find_operation(spec, cfg["operation_id"])

        # Patch the tool config with the resolved endpoint + method so
        # APIHandler can execute without modification.
        import copy

        patched_ctx_tool_def = copy.copy(ctx.tool_def)
        patched_config = dict(ctx.tool_def.config)
        patched_config["endpoint"] = self._build_url(spec, operation["path"])
        patched_config["method"] = operation["method"].upper()
        patched_ctx_tool_def.config = patched_config  # type: ignore[misc]
        ctx.tool_def = patched_ctx_tool_def  # type: ignore[misc]

        return await self._api_handler.execute(ctx)

    async def _load_spec(self, cfg: dict[str, Any]) -> dict[str, Any]:
        import json

        import httpx
        import yaml as _yaml

        key = cfg.get("spec_url") or cfg.get("spec_file", "")
        if key in self._spec_cache:
            return self._spec_cache[key]

        if cfg.get("spec_url"):
            async with httpx.AsyncClient() as client:
                resp = await client.get(cfg["spec_url"])
                resp.raise_for_status()
                text = resp.text
        else:
            from pathlib import Path

            text = Path(cfg["spec_file"]).read_text()

        try:
            spec = json.loads(text)
        except json.JSONDecodeError:
            spec = _yaml.safe_load(text)

        self._spec_cache[key] = spec
        return spec

    @staticmethod
    def _find_operation(spec: dict[str, Any], operation_id: str) -> dict[str, Any]:
        for path, path_item in spec.get("paths", {}).items():
            for method, operation in path_item.items():
                if isinstance(operation, dict) and operation.get("operationId") == operation_id:
                    return {"path": path, "method": method}
        raise ValueError(f"operationId '{operation_id}' not found in OpenAPI spec.")

    @staticmethod
    def _build_url(spec: dict[str, Any], path: str) -> str:
        servers = spec.get("servers", [{}])
        base = servers[0].get("url", "").rstrip("/")
        return f"{base}{path}"