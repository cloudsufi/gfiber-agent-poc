"""BigQueryHandler — executes SQL queries against Google BigQuery."""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from agent_tools.handlers.base import BaseHandler

if TYPE_CHECKING:
    from agent_tools.core.runtime import ExecutionContext


class BigQueryHandler(BaseHandler):
    """
    Runs a parameterised SQL query against BigQuery.

    Requires the ``bigquery`` extra: ``pip install "agent-tools[bigquery]"``.
    """

    async def execute(self, ctx: "ExecutionContext") -> Any:
        try:
            from google.cloud import bigquery  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "google-cloud-bigquery is required for BigQuery tools. "
                "Install with: pip install 'agent-tools[bigquery]'"
            ) from exc

        cfg = ctx.tool_def.config
        client = bigquery.Client(project=cfg.get("project"))
        query = cfg["query"].format(**ctx.validated_input)

        rows = await asyncio.to_thread(lambda: list(client.query(query).result()))

        max_results = cfg.get("max_results") or 0
        if max_results > 0:
            rows = rows[:max_results]

        return {"rows": [dict(r) for r in rows]}