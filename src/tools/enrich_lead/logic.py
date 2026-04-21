"""
Custom Python logic for the enrich_lead tool.

This module is loaded dynamically by PythonHandler at call time.
``run()`` must be an async function that accepts a dict and returns a dict.
"""
from __future__ import annotations

import os


async def run(inputs: dict) -> dict:
    """
    Enrich lead data.  In production this would call the Clearbit API.
    This example returns mock data so the tool works without credentials.
    """
    email = inputs.get("email", "")
    company = inputs.get("company", "")

    # In real usage: call Clearbit/Apollo/etc. using os.environ["CLEARBIT_KEY"]
    api_key = os.environ.get("CLEARBIT_KEY", "")  # noqa: F841

    return {
        "email":        email,
        "company_name": company or "Acme Corp",
        "industry":     "Technology",
        "location":     "San Francisco, CA",
        "employees":    250,
    }