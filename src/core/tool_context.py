"""
ToolContext — metadata carried through every tool call.

Contains session-level information (session ID, user identity, event type, timestamp)
that flows through the entire execution pipeline and into handler execution.

This is the **first positional parameter** for every tool call, both direct invocations
and ADK agent dispatches. It is never part of the LLM-facing schema.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class ToolContext:
    """Session metadata carried through tool execution.

    Fields:
        session_id: Unique session identifier for tracing tool calls across a session.
        hashed_user_id: SHA-256 hash of the user ID for privacy-preserving logging.
        event_type: Classification of the invocation (e.g. "adk_tool_call", "direct_call").
        timestamp: ISO-8601 timestamp of the call (UTC).
    """

    session_id: str = ""
    hashed_user_id: str = ""
    event_type: str = "tool_call"
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def __repr__(self) -> str:
        """Compact repr for safe logging (never dumps sensitive values)."""
        return (
            f"ToolContext(session={self.session_id[:8]}, "
            f"user={self.hashed_user_id[:8]}, "
            f"event={self.event_type})"
        )
