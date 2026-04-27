"""
OpenAPIHandler — executes a single operation from an OpenAPI 3.x spec.

For a tool with ``type: openapi``, the handler:

1. Loads the sibling ``openapi.yaml`` file (the full OpenAPI 3.x spec)
2. Looks up the operation by ``operationId`` from ``config.operation_id``
3. Resolves the server URL from spec or env var override
4. Routes validated input fields to path params / query params / request body
   based on the operation's parameter definitions
5. Makes an httpx request with auth + runtime headers
6. Returns the response JSON

Parameter routing:
- Fields with ``in: path`` become path parameters (substitute into URL)
- Fields with ``in: query`` become query string parameters
- Fields with ``in: header`` become HTTP headers
- Any field not in the operation's ``parameters`` list goes to request body (when
  ``requestBody`` is declared)

Authentication and runtime headers use the same pipeline as ``APIHandler``
— auth is resolved by ``AuthMiddleware`` and injected into ``ctx.resolved_auth``,
and runtime headers are filtered against ``config.runtime_headers`` allow-list.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

import httpx
import yaml

from agent_tools.core.context import current_request_headers
from agent_tools.handlers.api_handler import _inject_auth_headers
from agent_tools.handlers.base import BaseHandler

if TYPE_CHECKING:
    from agent_tools.core.runtime import ExecutionContext


class OpenAPIHandler(BaseHandler):
    """
    Executes a single operation from an OpenAPI 3.x specification.

    The tool directory must contain an ``openapi.yaml`` file with the spec.
    The operation is selected by ``config.operation_id``.
    """

    async def execute(self, ctx: ExecutionContext) -> Any:
        cfg = ctx.tool_def.config
        spec_path = ctx.tool_def.tool_dir / "openapi.yaml"

        if not spec_path.exists():
            raise FileNotFoundError(
                f"openapi.yaml not found for tool '{ctx.tool_def.name}': {spec_path}"
            )

        spec = yaml.safe_load(spec_path.read_text())

        # Resolve server URL
        server_url = _resolve_server_url(spec, cfg.get("server_url_env"))

        # Find the operation
        operation, method, path_template = _find_operation(spec, cfg["operation_id"])

        # Route validated_input to path / query / body
        params_spec = {p["name"]: p for p in operation.get("parameters", [])}
        path_params: dict[str, Any] = {}
        query_params: dict[str, Any] = {}
        body_fields: dict[str, Any] = {}
        header_params: dict[str, Any] = {}

        for k, v in ctx.validated_input.items():
            param_loc = params_spec.get(k, {}).get("in")
            if param_loc == "path":
                path_params[k] = v
            elif param_loc == "query":
                query_params[k] = v
            elif param_loc == "header":
                header_params[k] = v
            else:
                body_fields[k] = v

        # Build final URL by substituting path params (OpenAPI uses {param} single-brace)
        url = server_url + path_template
        for name, value in path_params.items():
            url = url.replace("{" + name + "}", str(value))

        # Build headers
        headers = dict(header_params)  # header parameters go directly to headers

        # Inject auth (same pattern as APIHandler)
        _inject_auth_headers(headers, ctx.resolved_auth)

        # Inject runtime headers (filtered by allow-list)
        runtime_hdr = current_request_headers()
        if runtime_hdr and cfg.get("runtime_headers"):
            allowed_lower = {h.lower() for h in cfg["runtime_headers"]}
            for k, v in runtime_hdr.items():
                if k.lower() in allowed_lower:
                    headers[k] = v

        # Set content type for JSON body if present
        if body_fields:
            headers.setdefault("Content-Type", "application/json")

        timeout = float(cfg.get("timeout_seconds") or 30)

        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            resp = await client.request(
                method=method.upper(),
                url=url,
                headers=headers,
                params=query_params or None,
                json=body_fields or None,
            )
            resp.raise_for_status()
            return resp.json()


def _resolve_server_url(spec: dict[str, Any], server_url_env: str | None) -> str:
    """
    Resolve the server URL from the spec or an env var override.

    :param spec: Parsed OpenAPI spec
    :param server_url_env: Optional env var name to override spec servers[0].url
    :return: Server URL (without trailing slash)
    """
    # Try env var first
    if server_url_env:
        env_url = os.environ.get(server_url_env, "").strip()
        if env_url:
            return env_url.rstrip("/")

    # Fall back to spec
    servers = spec.get("servers", [])
    if not servers:
        raise ValueError("No servers defined in OpenAPI spec and no server_url_env set")
    return servers[0]["url"].rstrip("/")


def _find_operation(
    spec: dict[str, Any], operation_id: str
) -> tuple[dict[str, Any], str, str]:
    """
    Find an operation in the spec by operationId.

    :param spec: Parsed OpenAPI spec
    :param operation_id: The operationId to find
    :return: Tuple of (operation dict, HTTP method, path template)
    :raises ValueError: If operation not found
    """
    methods = ("get", "post", "put", "patch", "delete", "head", "options")
    for path_template, path_item in spec.get("paths", {}).items():
        for method in methods:
            operation = path_item.get(method)
            if operation and operation.get("operationId") == operation_id:
                return operation, method, path_template

    raise ValueError(
        f"Operation '{operation_id}' not found in OpenAPI spec. "
        f"Available operations: {_list_operations(spec)}"
    )


def _list_operations(spec: dict[str, Any]) -> list[str]:
    """Extract all operationIds from the spec for error messages."""
    ops = []
    methods = ("get", "post", "put", "patch", "delete", "head", "options")
    for path_item in spec.get("paths", {}).values():
        for method in methods:
            op = path_item.get(method)
            if op and op.get("operationId"):
                ops.append(op["operationId"])
    return ops
