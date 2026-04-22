"""
Runnable demo — exercises all four primary tool types end-to-end.

Sections:

1. Discovery        — every tool.yaml on disk appears as a top-level callable
2. JSON schemas     — what an LLM / ADK agent receives for each tool
3. API tool         — ``weather_api``  (real HTTP to httpbin.org + templated params/headers + bearer auth)
4. MCP tool         — ``docs_mcp``     (mock_mode — deterministic echo)
5. Function tool    — ``score_function`` (Python logic.py + static parameters)
6. CTA tool         — ``support_cta``  (Dialogflow CX — mock_mode response)
7. Dynamic headers  — block-scoped + ``_headers=`` kwarg
8. ADK LlmAgent     — optional, behind ``--adk`` (requires google-adk)

Run::

    python test_agent/demo.py           # sections 1-7
    python test_agent/demo.py --adk     # + ADK agent (needs google-adk)
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import warnings
from pathlib import Path

# Silence noisy third-party warnings (authlib deprecation, ADK experimental).
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=UserWarning, module=r"google\.adk.*")

# Make sibling modules importable under both ``python test_agent/demo.py`` and
# ``python -m test_agent.demo``.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

# Demo-time env vars consumed by weather_api's tool.yaml.
os.environ.setdefault("WEATHER_API_KEY", "demo-bearer-token")
os.environ.setdefault("AGENT_ENV", "local-demo")

from agent_tools import (  # noqa: E402
    docs_mcp,
    score_function,
    support_cta,
    weather_api,
    with_request_headers,
)


def section(title: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


def pretty(obj: object) -> str:
    return json.dumps(obj, indent=2, default=str)


async def demo_discovery() -> None:
    section("1. Auto-discovered tools (from src/tools/)")
    print("Registered tools:", sorted(t.__name__ for t in weather_api.all_tools()))


async def demo_schemas() -> None:
    section("2. JSON schemas (derived from each tool's request.proto)")
    for schema in weather_api.all_schemas():
        print(f"\n— {schema['name']} —")
        print(pretty(schema["parameters"]))


async def demo_api_tool() -> None:
    section("3. API tool — weather_api (real HTTP via httpbin.org)")
    try:
        result = await weather_api(city="London", units="metric", trace_id="trace-001")
    except Exception as exc:  # network offline, httpbin flaky, etc.
        print(f"Skipping — HTTP call failed: {exc}")
        return
    print("Resolved URL        :", result["url"])
    print("Echoed query args   :", result["args"])
    print("X-Trace-Id header   :", result["headers"].get("X-Trace-Id"))
    print("X-Agent-Env header  :", result["headers"].get("X-Agent-Env"))
    print("Authorization header:", result["headers"].get("Authorization"))


async def demo_mcp_tool() -> None:
    section("4. MCP tool — docs_mcp (mock_mode — no MCP server needed)")
    result = await docs_mcp(query="onboarding checklist", top_k=3, filter_tag="docs")
    print(pretty(result))


async def demo_function_tool() -> None:
    section("5. Function tool — score_function (local Python logic.py)")
    result = await score_function(
        email="ada@example.com",
        company="Example Corp",
        annual_spend=25_000,
        region="us-west",
    )
    print(pretty(result))


async def demo_cta_tool() -> None:
    section("6. CTA tool — support_cta (Dialogflow CX — mock_mode response)")
    result = await support_cta(text="Where is my order?", session_id="session-abc")
    print(pretty(result))


async def demo_dynamic_headers() -> None:
    section("7. Runtime header injection (only for allow-listed names)")
    print(
        "weather_api's tool.yaml declares `runtime_headers: [X-Trace-Id]`, "
        "so only X-Trace-Id can be overridden from agent code. X-Secret is "
        "intentionally NOT in the allow-list and will be dropped.\n"
    )

    # (a) Block-scoped — applies to every tool call inside the with-block.
    try:
        with with_request_headers(
            {"X-Trace-Id": "scoped-trace", "X-Secret": "should-not-leak"}
        ):
            r = await weather_api(city="Tokyo", units="metric", trace_id="tool-trace")
        print("X-Trace-Id (allow-listed, runtime wins):", r["headers"].get("X-Trace-Id"))
        print("X-Secret   (not allow-listed, dropped) :", r["headers"].get("X-Secret"))
    except Exception as exc:
        print(f"Skipping block-scoped demo — HTTP offline: {exc}")

    # (b) One-shot via _headers= kwarg.
    try:
        r = await weather_api(
            city="Berlin",
            units="metric",
            trace_id="tool-trace-2",
            _headers={"X-Trace-Id": "one-shot-trace", "X-Rogue": "dropped"},
        )
        print("_headers= X-Trace-Id                   :", r["headers"].get("X-Trace-Id"))
        print("_headers= X-Rogue (not allow-listed)   :", r["headers"].get("X-Rogue"))
    except Exception as exc:
        print(f"Skipping _headers= demo — HTTP offline: {exc}")


async def demo_adk_agent() -> None:
    section("8. ADK agent wiring (requires google-adk)")
    from agent import build_agent

    try:
        agent = build_agent()
    except ImportError as exc:
        print(f"Skipping — google-adk not installed: {exc}")
        print("Install with: pip install google-adk")
        return

    print("Built agent :", agent.name)
    print("  model     :", agent.model)
    print("  tool count:", len(agent.tools))
    print("  tool names:", sorted(t.name for t in agent.tools))


async def main() -> None:
    await demo_discovery()
    await demo_schemas()
    await demo_api_tool()
    await demo_mcp_tool()
    await demo_function_tool()
    await demo_cta_tool()
    await demo_dynamic_headers()
    if "--adk" in sys.argv:
        await demo_adk_agent()
    else:
        print("\n(Pass --adk to build an LlmAgent over every registered tool.)")


if __name__ == "__main__":
    asyncio.run(main())
