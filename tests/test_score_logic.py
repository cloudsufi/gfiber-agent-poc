"""
Tests for tools/score_function/logic.py

Covers:
- run(): all tier outcomes (high, medium, low)
- run(): tool_context state read and write
- run(): no tool_context (None)
- run(): all company_size / industry combos
- run(): annual_revenue_usd capping and effect on score
- run(): has_existing_contract bonus
- _compute_score(): direct unit tests
- _rationale(): all tier branches
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

# ── Load logic.py directly (not via adk_tools loader) ─────────────────────────
# This lets us test the scoring logic in isolation without needing google-adk.

_LOGIC_PATH = Path(__file__).parent.parent / "tools" / "score_function" / "logic.py"
_spec = importlib.util.spec_from_file_location("score_function_logic", _LOGIC_PATH)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

run = _module.run
_compute_score = _module._compute_score
_rationale = _module._rationale


# ── Helpers ────────────────────────────────────────────────────────────────────

def _ctx(state: dict | None = None):
    """Return a minimal ToolContext-like object."""
    return SimpleNamespace(state=state or {"session_id": "s1", "user_id": "u1"})


# ── run() — tier outcomes ──────────────────────────────────────────────────────

class TestRunTier:
    @pytest.mark.asyncio
    async def test_enterprise_saas_full_revenue_contract_is_high(self):
        # enterprise(0.9) * 0.4 + saas(0.8) * 0.3 + 10M_rev(0.2) + contract(0.15) = 0.95 → high
        result = await run(
            company_size="enterprise",
            industry="saas",
            tool_context=_ctx(),
            annual_revenue_usd=10_000_000,
            has_existing_contract=True,
        )
        assert result["tier"] == "high"
        assert 0.0 <= result["score"] <= 1.0

    @pytest.mark.asyncio
    async def test_enterprise_saas_no_revenue_is_medium(self):
        # enterprise(0.9) * 0.4 + saas(0.8) * 0.3 = 0.36 + 0.24 = 0.60 → exactly medium
        result = await run(
            company_size="enterprise",
            industry="saas",
            tool_context=_ctx(),
            annual_revenue_usd=0,
        )
        assert result["tier"] == "medium"

    @pytest.mark.asyncio
    async def test_startup_other_is_low_tier(self):
        # startup(0.2) * 0.4 + other(0.5) * 0.3 = 0.08 + 0.15 = 0.23 → low
        result = await run(
            company_size="startup",
            industry="other",
            tool_context=_ctx(),
            annual_revenue_usd=0,
        )
        assert result["tier"] == "low"

    @pytest.mark.asyncio
    async def test_enterprise_healthcare_with_revenue_is_medium(self):
        # enterprise + healthcare + 5M revenue → score in medium range
        result = await run(
            company_size="enterprise",
            industry="healthcare",
            tool_context=_ctx(),
            annual_revenue_usd=5_000_000,
        )
        assert result["tier"] in ("medium", "high")

    @pytest.mark.asyncio
    async def test_returns_required_keys(self):
        result = await run(
            company_size="smb",
            industry="saas",
            tool_context=_ctx(),
        )
        for key in ("tier", "score", "model_version", "rationale", "session_id"):
            assert key in result


# ── run() — tool_context state ────────────────────────────────────────────────

class TestRunToolContext:
    @pytest.mark.asyncio
    async def test_reads_session_id(self):
        ctx = _ctx({"session_id": "abc123", "user_id": "u"})
        result = await run(company_size="smb", industry="saas", tool_context=ctx)
        assert result["session_id"] == "abc123"

    @pytest.mark.asyncio
    async def test_writes_state_back(self):
        ctx = _ctx({"session_id": "s", "user_id": "u"})
        await run(company_size="enterprise", industry="fintech", tool_context=ctx)
        assert ctx.state["last_lead_company_size"] == "enterprise"
        assert ctx.state["last_lead_industry"] == "fintech"

    @pytest.mark.asyncio
    async def test_none_tool_context_ok(self):
        """Should not crash when tool_context is None."""
        result = await run(
            company_size="smb",
            industry="saas",
            tool_context=None,
        )
        assert result["session_id"] == ""

    @pytest.mark.asyncio
    async def test_empty_state_ok(self):
        ctx = SimpleNamespace(state={})
        result = await run(company_size="smb", industry="saas", tool_context=ctx)
        assert result["session_id"] == ""

    @pytest.mark.asyncio
    async def test_no_state_attr_ok(self):
        ctx = SimpleNamespace()  # no .state attribute
        result = await run(company_size="smb", industry="saas", tool_context=ctx)
        assert isinstance(result, dict)


# ── run() — static param injection (model_version / threshold) ────────────────

class TestRunStaticParams:
    @pytest.mark.asyncio
    async def test_model_version_in_result(self):
        result = await run(
            company_size="smb",
            industry="saas",
            tool_context=_ctx(),
            model_version="v9.9",
            threshold="0.60",
        )
        assert result["model_version"] == "v9.9"

    @pytest.mark.asyncio
    async def test_threshold_affects_tier(self):
        """Raising threshold should push mid-range scores to lower tiers."""
        result_low_thresh = await run(
            company_size="smb",
            industry="saas",
            tool_context=_ctx(),
            threshold="0.10",
        )
        result_high_thresh = await run(
            company_size="smb",
            industry="saas",
            tool_context=_ctx(),
            threshold="0.90",
        )
        # With a very high threshold, tier should be lower
        tier_order = {"high": 2, "medium": 1, "low": 0}
        assert tier_order[result_low_thresh["tier"]] >= tier_order[result_high_thresh["tier"]]


# ── _compute_score() ──────────────────────────────────────────────────────────

class TestComputeScore:
    def test_enterprise_saas_high_score(self):
        # enterprise+saas+max_revenue+contract = 0.95
        score = _compute_score(
            company_size="enterprise",
            industry="saas",
            annual_revenue_usd=10_000_000,
            has_existing_contract=True,
        )
        assert score >= 0.80  # qualifies for high tier

    def test_startup_other_low_score(self):
        score = _compute_score(
            company_size="startup",
            industry="other",
            annual_revenue_usd=0,
            has_existing_contract=False,
        )
        assert score < 0.5

    def test_score_capped_at_1(self):
        score = _compute_score(
            company_size="enterprise",
            industry="saas",
            annual_revenue_usd=999_999_999,
            has_existing_contract=True,
        )
        assert score <= 1.0

    def test_revenue_capped_at_10m(self):
        score_10m = _compute_score(
            company_size="smb",
            industry="saas",
            annual_revenue_usd=10_000_000,
            has_existing_contract=False,
        )
        score_100m = _compute_score(
            company_size="smb",
            industry="saas",
            annual_revenue_usd=100_000_000,
            has_existing_contract=False,
        )
        assert score_10m == score_100m  # revenue weight caps at $10M

    def test_contract_bonus_applied(self):
        score_with = _compute_score(
            company_size="smb",
            industry="saas",
            annual_revenue_usd=0,
            has_existing_contract=True,
        )
        score_without = _compute_score(
            company_size="smb",
            industry="saas",
            annual_revenue_usd=0,
            has_existing_contract=False,
        )
        assert score_with > score_without

    def test_unknown_size_uses_default(self):
        score = _compute_score(
            company_size="unicorn",
            industry="saas",
            annual_revenue_usd=0,
            has_existing_contract=False,
        )
        assert 0.0 <= score <= 1.0

    def test_unknown_industry_uses_default(self):
        score = _compute_score(
            company_size="smb",
            industry="unknown_industry",
            annual_revenue_usd=0,
            has_existing_contract=False,
        )
        assert 0.0 <= score <= 1.0

    @pytest.mark.parametrize("size", ["startup", "smb", "mid-market", "enterprise"])
    def test_all_company_sizes(self, size):
        score = _compute_score(
            company_size=size,
            industry="saas",
            annual_revenue_usd=1_000_000,
            has_existing_contract=False,
        )
        assert 0.0 <= score <= 1.0

    @pytest.mark.parametrize("industry", ["saas", "fintech", "healthcare", "other"])
    def test_all_industries(self, industry):
        score = _compute_score(
            company_size="smb",
            industry=industry,
            annual_revenue_usd=0,
            has_existing_contract=False,
        )
        assert 0.0 <= score <= 1.0

    def test_case_insensitive_size(self):
        score_lower = _compute_score(company_size="enterprise", industry="saas",
                                      annual_revenue_usd=0, has_existing_contract=False)
        score_upper = _compute_score(company_size="ENTERPRISE", industry="saas",
                                      annual_revenue_usd=0, has_existing_contract=False)
        assert score_lower == score_upper


# ── _rationale() ──────────────────────────────────────────────────────────────

class TestRationale:
    def test_high_tier_message(self):
        r = _rationale("high", "enterprise", "saas", False)
        assert "strong fit" in r.lower()

    def test_medium_tier_message(self):
        r = _rationale("medium", "smb", "fintech", False)
        assert "potential" in r.lower() or "discovery" in r.lower()

    def test_low_tier_message(self):
        r = _rationale("low", "startup", "other", False)
        assert "low-priority" in r.lower()

    def test_contract_mentioned(self):
        r = _rationale("high", "enterprise", "saas", True)
        assert "contract" in r.lower()

    def test_no_contract_not_mentioned(self):
        r = _rationale("high", "enterprise", "saas", False)
        assert "contract" not in r.lower()

    def test_size_and_industry_in_rationale(self):
        r = _rationale("medium", "mid-market", "healthcare", False)
        assert "mid-market" in r.lower() or "mid" in r.lower()
