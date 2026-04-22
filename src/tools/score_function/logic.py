"""
Function logic for ``score_function``.

Framework contract: FunctionHandler imports this module, finds ``run`` and
awaits it. ``inputs`` merges the validated request proto with the static
``parameters`` map from tool.yaml.
"""
from __future__ import annotations


async def run(inputs: dict) -> dict:
    email = inputs.get("email", "")
    company = inputs.get("company", "")
    spend = int(inputs.get("annual_spend", 0) or 0)
    region = inputs.get("region", "")

    threshold = float(inputs.get("threshold", "0.5") or 0.5)
    model_version = inputs.get("model_version", "v1.0")

    # Toy scoring rules — purely for demo purposes.
    score = 0.3
    if spend >= 50_000:
        score += 0.35
    elif spend >= 10_000:
        score += 0.2
    if region in {"us-east", "us-west", "eu-west"}:
        score += 0.15
    if company:
        score += 0.1
    score = min(round(score, 2), 1.0)

    tier = "A" if score >= 0.8 else "B" if score >= 0.6 else "C"

    return {
        "email":           email,
        "score":           score,
        "tier":            tier,
        "model_version":   model_version,
        "above_threshold": score >= threshold,
    }
