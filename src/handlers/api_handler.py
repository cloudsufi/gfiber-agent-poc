"""
APIHandler — executes HTTP API calls using httpx.

Design
------
An ``api`` tool is described in yaml by its endpoint, method, optional
``headers`` / ``params`` / ``body_template``, auth block, and — new —
``runtime_headers`` opt-in list. The handler's job is to assemble all of
those into a single ``httpx.AsyncClient.request`` call.

Header sources and precedence
-----------------------------
Headers come from four places. Later sources override earlier ones on
name conflict::

    1. Static ``headers:`` from tool.yaml            (always applied)
    2. Templated values in the same map              (always applied, same dict)
       {{field}}   ← pulled from ctx.validated_input
       {{env:VAR}} ← pulled from os.environ
       A header whose template can't resolve is skipped silently.
    3. Auth headers injected by AuthMiddleware       (always applied)
       e.g. Authorization: Bearer <resolved-token>
    4. Runtime-supplied headers                      (opt-in only)
       From with_request_headers(...) or _headers= kwarg.
       Filtered by the tool's ``runtime_headers`` allow-list.
       Without that list, this whole source is ignored.

Params and body templating
--------------------------
``params`` and ``body_template`` values support the same ``{{field}}`` /
``{{env:VAR}}`` syntax. Resolution is done by ``_resolve_tokens``, which
returns ``None`` when any token is unresolvable (the param/body is then
skipped rather than sent with literal ``{{...}}`` in it).

HTTP semantics
--------------
* ``trust_env=False`` on the client — the framework ignores system-level
  ``HTTP_PROXY`` / ``HTTPS_PROXY`` env vars because they've caused more
  surprise than benefit in agent deployments. Set proxies explicitly in
  your client config if you need them.
* ``resp.raise_for_status()`` — HTTP 4xx/5xx becomes an exception, which
  the retry middleware may retry depending on the tool's ``retries``
  setting.
"""
from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, Any, Mapping

from agent_tools.core.context import current_request_headers
from agent_tools.handlers.base import BaseHandler

if TYPE_CHECKING:
    from agent_tools.core.runtime import ExecutionContext


_TEMPLATE_TOKEN = re.compile(r"\{\{\s*(env:)?([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


class APIHandler(BaseHandler):
    """
    Executes REST/HTTP API tools.

    Headers are assembled from four sources, later sources overriding earlier
    ones on key conflicts:

    1. Static ``headers:`` from ``tool.yaml``
    2. Templated values in those same headers — ``{{field}}`` pulls from the
       validated request input; ``{{env:VAR}}`` pulls from the process env
    3. Auth headers from :class:`~agent_tools.middleware.auth.AuthMiddleware`
    4. Request-scoped headers from
       :func:`agent_tools.core.context.with_request_headers` or the
       ``_headers=`` kwarg — **only if** the tool declares
       ``runtime_headers:`` in its config (case-insensitive allow-list).
       Without that declaration, runtime headers are ignored entirely.
    """

    async def execute(self, ctx: "ExecutionContext") -> Any:
        import httpx

        cfg = ctx.tool_def.config
        headers = _render_headers(cfg.get("headers", {}), ctx.validated_input)
        _inject_auth_headers(headers, ctx.resolved_auth)
        headers.update(
            _filter_runtime_headers(
                current_request_headers(),
                cfg.get("runtime_headers", []),
            )
        )

        timeout = cfg.get("timeout_seconds") or ctx.tool_def.execution.timeout
        method = cfg.get("method", "GET").upper()

        params = {
            k: (_resolve_tokens(v, ctx.validated_input) or "") if isinstance(v, str) else v
            for k, v in cfg.get("params", {}).items()
        }

        body: Any = None
        if method != "GET" and cfg.get("body_template"):
            import json

            rendered_body = _resolve_tokens(cfg["body_template"], ctx.validated_input)
            if rendered_body is not None:
                body = json.loads(rendered_body)

        async with httpx.AsyncClient(
            timeout=float(timeout or 30),
            trust_env=False,
        ) as client:
            resp = await client.request(
                method=method,
                url=cfg["endpoint"],
                headers=headers,
                params=params,
                json=body,
            )
            resp.raise_for_status()
            return resp.json()


def _filter_runtime_headers(
    runtime: Mapping[str, str],
    allow_list: list[str] | None,
) -> dict[str, str]:
    """
    Keep only headers in *runtime* whose names appear in *allow_list*.

    Comparison is case-insensitive. An empty/missing allow list means the
    tool did not opt in to runtime headers, so nothing passes through.
    """
    if not runtime or not allow_list:
        return {}
    allowed_lower = {name.lower() for name in allow_list}
    return {k: v for k, v in runtime.items() if k.lower() in allowed_lower}


def _inject_auth_headers(headers: dict[str, str], auth: dict[str, Any]) -> None:
    """Mutate *headers* in-place with the resolved auth credential."""
    auth_type = auth.get("type")
    if auth_type == "bearer":
        headers["Authorization"] = f"Bearer {auth['token']}"
    elif auth_type == "api_key":
        headers[auth["header"]] = auth["value"]
    elif auth_type == "basic":
        headers["Authorization"] = f"Basic {auth['encoded']}"


def _render_headers(
    raw: Mapping[str, str],
    input_fields: Mapping[str, Any],
) -> dict[str, str]:
    """
    Render ``{{field}}`` and ``{{env:VAR}}`` tokens in header values.

    A header is skipped entirely if any of its tokens cannot be resolved —
    an unset env var or a request field that wasn't supplied. This keeps
    literal ``{{...}}`` out of outgoing requests and makes optional headers
    (e.g. trace IDs only present in some calls) safe to declare statically.
    """
    rendered: dict[str, str] = {}
    for name, value in raw.items():
        if not isinstance(value, str):
            rendered[name] = value
            continue
        resolved = _resolve_tokens(value, input_fields)
        if resolved is not None:
            rendered[name] = resolved
    return rendered


def _resolve_tokens(
    value: str,
    input_fields: Mapping[str, Any],
) -> str | None:
    """Replace template tokens in *value*; return None if any token is missing."""
    missing = False

    def repl(match: re.Match[str]) -> str:
        nonlocal missing
        is_env = match.group(1) == "env:"
        name = match.group(2)
        if is_env:
            env_value = os.environ.get(name)
            if env_value is None:
                missing = True
                return ""
            return env_value
        if name not in input_fields:
            missing = True
            return ""
        return str(input_fields[name])

    result = _TEMPLATE_TOKEN.sub(repl, value)
    return None if missing else result
