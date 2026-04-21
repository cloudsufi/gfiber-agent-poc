"""
Request-scoped context — carries per-call HTTP header overrides from agent
code into tool execution.

Headers registered here are merged into the outgoing request by
:class:`agent_tools.handlers.api_handler.APIHandler`, taking precedence over
static ``headers:`` values in ``tool.yaml`` and over auth-injected headers.

Usage
-----

Scope — applies to every tool call within the block (async-safe, isolated
per :mod:`contextvars` token)::

    from agent_tools import with_request_headers, enrich_lead

    with with_request_headers({"X-Tenant-Id": tenant, "X-Trace-Id": trace}):
        result = await enrich_lead(domain="stripe.com")

One-shot — applies only to this call::

    result = await enrich_lead(
        domain="stripe.com",
        _headers={"X-Trace-Id": "abc"},
    )
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Mapping

_request_headers_var: ContextVar[dict[str, str]] = ContextVar(
    "agent_tools_request_headers", default={}
)


def current_request_headers() -> dict[str, str]:
    """Return a copy of the currently-scoped request headers."""
    return dict(_request_headers_var.get())


@contextmanager
def with_request_headers(headers: Mapping[str, str]) -> Iterator[None]:
    """Merge *headers* into the request-scoped header context for this block."""
    merged = {**_request_headers_var.get(), **headers}
    token = _request_headers_var.set(merged)
    try:
        yield
    finally:
        _request_headers_var.reset(token)
