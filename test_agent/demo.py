"""
Runnable demo — showcases the ai-agent-shared-tools framework end-to-end.

What this demonstrates (no ADK required for the first four sections):

1. Auto-discovery         — tools appear as top-level imports with zero config
2. JSON-Schema exposure   — each tool carries the schema an LLM needs
3. Direct tool call       — awaitable like a plain Python async function
4. Dynamic header paths   — templated, env-var, and runtime-injected headers
5. ADK agent wiring       — guarded behind an `--adk` flag (needs google-adk)

Run::

    python test_agent/demo.py                # sections 1-4
    python test_agent/demo.py --adk          # sections 1-5 (requires google-adk)
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import warnings
from pathlib import Path

# Silence noisy third-party warnings (authlib deprecation, ADK experimental
# feature notices) so the demo output stays focused on framework behaviour.
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=UserWarning, module=r"google\.adk.*")
try:
    from authlib.deprecate import AuthlibDeprecationWarning  # type: ignore

    warnings.filterwarnings("ignore", category=AuthlibDeprecationWarning)
except ImportError:
    pass

# Make sibling modules (agent.py) importable whether this file is run as
# ``python test_agent/demo.py`` or ``python -m test_agent.demo``.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from agent_tools import (
    enrich_lead,
    with_request_headers,
)


def section(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


async def demo_registry() -> None:
    section("1. Auto-discovered tools")
    names = [t.__name__ for t in enrich_lead.all_tools()]
    print(f"Registered tools: {names}")


async def demo_schemas() -> None:
    section("2. LLM / ADK JSON schemas (derived from request.proto)")
    for schema in enrich_lead.all_schemas():
        print(json.dumps(schema, indent=2))


async def demo_direct_call() -> None:
    section("3. Direct tool call — enrich_lead (mock logic, no network)")
    result = await enrich_lead(
        email="ada@example.com",
        company="Example Corp",
    )
    print(json.dumps(result, indent=2))


async def demo_dynamic_headers() -> None:
    section("4. Dynamic header injection (block-scoped + _headers kwarg)")

    # (a) Set an env var that could be referenced from tool.yaml as {{env:TRACE_SRC}}
    os.environ["TRACE_SRC"] = "demo-script"

    # (b) Block-scoped — every tool call inside sees these headers
    with with_request_headers({"X-Trace-Id": "trace-abc-123"}):
        result = await enrich_lead(email="scope@example.com", company="ScopeCo")
        print(f"inside with_request_headers → {result['email']}")

    # (c) One-shot — reserved _headers kwarg on the call itself
    result = await enrich_lead(
        email="oneshot@example.com",
        company="OneShotCo",
        _headers={"X-Trace-Id": "trace-xyz-789"},
    )
    print(f"with _headers= kwarg       → {result['email']}")

    print(
        "\nNote: enrich_lead is a python-type tool, so headers aren't sent "
        "over the wire here — but the exact same API works for any api / rest "
        "tool, where APIHandler merges them into the outgoing HTTP request."
    )


async def demo_adk_agent() -> None:
    section("5. ADK agent wiring (requires google-adk)")

    # Import the sibling agent module. The sys.path shim at the top of this
    # file makes this work whether the demo is run as a script or as -m.
    from agent import build_agent

    try:
        agent = build_agent()
    except ImportError as exc:
        print(f"Skipping — google-adk not installed: {exc}")
        print("Install with: pip install google-adk")
        return

    print(f"Built agent: {agent.name}")
    print(f"  model       = {agent.model}")
    print(f"  tool count  = {len(agent.tools)}")
    print(f"  tool names  = {[t.name for t in agent.tools]}")


async def main() -> None:
    await demo_registry()
    await demo_schemas()
    await demo_direct_call()
    await demo_dynamic_headers()
    if "--adk" in sys.argv:
        await demo_adk_agent()
    else:
        print("\n(Pass --adk to also build the LlmAgent — needs google-adk installed)")


if __name__ == "__main__":
    asyncio.run(main())
