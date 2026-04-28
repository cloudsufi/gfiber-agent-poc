"""
Lead scoring logic for the score_function tool.

ADK builds the LLM tool schema from this function's signature + docstring.
Parameters injected by the framework (``model_version``, ``threshold`` from
``tool.yaml config.parameters``) are hidden from the schema — they are
pre-filled server-side before ADK calls the function.

``tool_context`` is typed as ``google.adk.tools.tool_context.ToolContext``.
ADK recognises this parameter by name and type and injects the live session
context automatically — it is never exposed to the LLM.

Usage (called automatically by ADK via FunctionTool):
    result = await run(
        company_size="enterprise",
        industry="saas",
        tool_context=<injected by ADK>,
        # model_version and threshold injected by adk_tools framework
    )
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

try:
    from google.adk.tools.tool_context import ToolContext  # type: ignore[import]
except ImportError:
    # Allow importing this file in environments without google-adk installed
    # (e.g. unit tests, CI).  The function still works; tool_context is just Any.
    ToolContext = object  # type: ignore[assignment, misc]


async def run(
    company_size: str,
    industry: str,
    tool_context: ToolContext,
    annual_revenue_usd: int = 0,
    has_existing_contract: bool = False,
    # ── Injected by adk_tools from tool.yaml config.parameters ───────────────
    # These never appear in the LLM schema.
    model_version: str = "v2.3",
    threshold: str = "0.60",
) -> dict:
    """
    Score a sales lead and return a priority tier with confidence.

    Args:
        company_size: Size category — "startup", "smb", "mid-market", or "enterprise".
        industry: Industry vertical (e.g. "saas", "fintech", "healthcare").
        annual_revenue_usd: Estimated annual revenue in USD (0 if unknown).
        has_existing_contract: True if the lead has an active contract already.

    Returns:
        dict with keys: tier (str), score (float 0–1), rationale (str),
        model_version (str), session_id (str).
    """
    # ── Access session state from ToolContext ─────────────────────────────────
    # tool_context.state is a dict-like object shared across all tools in the
    # current session.  You can read from it, write to it, and the changes are
    # visible to other tools called in the same turn.
    session_id = ""
    user_id = ""
    if tool_context is not None and hasattr(tool_context, "state") and tool_context.state:
        session_id = tool_context.state.get("session_id", "")
        user_id = tool_context.state.get("user_id", "")

        # Write scoring result back to session state so other tools can read it.
        # (e.g. a downstream personalise_outreach tool could check this.)
        tool_context.state["last_lead_company_size"] = company_size
        tool_context.state["last_lead_industry"] = industry

    log.debug(
        "score_function: session=%s user=%s company_size=%s industry=%s",
        session_id, user_id, company_size, industry,
    )

    # ── Scoring logic ─────────────────────────────────────────────────────────
    score = _compute_score(
        company_size=company_size,
        industry=industry,
        annual_revenue_usd=annual_revenue_usd,
        has_existing_contract=has_existing_contract,
    )
    threshold_val = float(threshold)
    tier = (
        "high"   if score >= threshold_val + 0.2 else
        "medium" if score >= threshold_val        else
        "low"
    )

    return {
        "tier": tier,
        "score": round(score, 3),
        "model_version": model_version,
        "rationale": _rationale(tier, company_size, industry, has_existing_contract),
        "session_id": session_id,
    }


# ── Internal helpers ───────────────────────────────────────────────────────────

_SIZE_WEIGHT     = {"startup": 0.2, "smb": 0.4, "mid-market": 0.6, "enterprise": 0.9}
_INDUSTRY_WEIGHT = {"saas": 0.8, "fintech": 0.75, "healthcare": 0.7, "other": 0.5}


def _compute_score(
    *,
    company_size: str,
    industry: str,
    annual_revenue_usd: int,
    has_existing_contract: bool,
) -> float:
    size_w     = _SIZE_WEIGHT.get(company_size.lower(), 0.3)
    industry_w = _INDUSTRY_WEIGHT.get(industry.lower(), 0.5)
    revenue_w  = min(annual_revenue_usd / 10_000_000, 1.0) * 0.2   # caps at $10M
    contract_b = 0.15 if has_existing_contract else 0.0
    raw = (size_w * 0.4) + (industry_w * 0.3) + revenue_w + contract_b
    return min(round(raw, 4), 1.0)


def _rationale(tier: str, size: str, industry: str, contract: bool) -> str:
    base   = f"{size.title()} {industry} company"
    extras = " with existing contract" if contract else ""
    if tier == "high":
        return f"{base}{extras} is a strong fit — prioritise immediately."
    if tier == "medium":
        return f"{base}{extras} shows good potential — schedule a discovery call."
    return f"{base}{extras} is a low-priority lead at this time."
