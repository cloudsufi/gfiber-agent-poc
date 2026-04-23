"""
Request-scoped context — carries per-call HTTP header overrides from agent
code into tool execution.

Headers registered here are merged into the outgoing request by
:class:`agent_tools.handlers.api_handler.APIHandler`, but **only** for
header names that the tool declared on its yaml ``runtime_headers`` allow
list. Anything the agent passes that isn't on the list is silently dropped
before the HTTP call. This keeps agent code from accidentally (or
maliciously) overriding headers a tool didn't design for — including auth.

Implementation
--------------
The mechanism is a ``contextvars.ContextVar[dict]``. ``ContextVar`` is
coroutine- and thread-safe: each ``asyncio.Task`` gets its own copy of the
value, so concurrent calls don't leak headers between each other.
:func:`with_request_headers` uses the ``set`` / ``reset`` token pattern so
nested blocks stack (inner entries override outer ones while the block is
active; outer entries are restored afterwards).

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

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar

_request_headers_var: ContextVar[dict[str, str] | None] = ContextVar(
    "agent_tools_request_headers", default=None
)


def current_request_headers() -> dict[str, str]:
    """Return a copy of the currently-scoped request headers."""
    return dict(_request_headers_var.get() or {})


@contextmanager
def with_request_headers(headers: Mapping[str, str]) -> Iterator[None]:
    """Merge *headers* into the request-scoped header context for this block."""
    merged = {**(_request_headers_var.get() or {}), **headers}
    token = _request_headers_var.set(merged)
    try:
        yield
    finally:
        _request_headers_var.reset(token)
