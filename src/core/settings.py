"""
Runtime settings, driven entirely by environment variables.

:class:`Settings` is an immutable, process-wide singleton. It's read once at
framework startup and never consulted again for its own values — later
layers (middleware, handlers) receive the resolved values as constructor
arguments.

Environment variables
---------------------
========================  ==========================================  =========
``AGENT_TOOLS_DIR``       Path to the directory containing tool.yaml  defaults
                          folders. Defaults to the package's own       to
                          ``src/tools/`` so the framework works         ``src/
                          without configuration.                        tools``
``AGENT_TOOLS_TIMEOUT``   Default per-call timeout in seconds for      30
                          HTTP / RPC handlers. Tools can override
                          via ``execution.timeout``.
``AGENT_TOOLS_RETRIES``   Default retry count used by
                          :class:`RetryMiddleware` when the tool       3
                          doesn't override it.
``AGENT_TOOLS_LOG_LEVEL`` Python logging level passed to               "INFO"
                          ``logging.basicConfig`` during
                          :class:`LoggingMiddleware` startup.
========================  ==========================================  =========

All env reads happen in :meth:`Settings.load`, which is ``lru_cache``-d —
subsequent calls return the same frozen instance. Tests clear the cache
via :meth:`Settings._reset` between runs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

# Package root → agent_tools/  (two levels up from this file)
_PACKAGE_ROOT: Path = Path(__file__).parent.parent


@dataclass(frozen=True)
class Settings:
    """
    Immutable settings singleton.  Resolved once at startup via :meth:`load`.

    All values are read from ``AGENT_TOOLS_*`` env vars.
    ``tools_dir`` defaults to the package's own ``tools/`` directory so the
    package works out-of-the-box with no env vars set.
    """

    tools_dir: Path = _PACKAGE_ROOT / "tools"
    default_timeout: int = 30
    default_retries: int = 3
    log_level: str = "INFO"

    @classmethod
    @lru_cache(maxsize=1)
    def load(cls) -> Settings:
        """
        Read environment and return a frozen :class:`Settings` instance.
        Cached — calling this multiple times returns the same object.
        """
        override = os.getenv("AGENT_TOOLS_DIR")
        return cls(
            tools_dir=Path(override) if override else _PACKAGE_ROOT / "tools",
            default_timeout=int(os.getenv("AGENT_TOOLS_TIMEOUT", "30")),
            default_retries=int(os.getenv("AGENT_TOOLS_RETRIES", "3")),
            log_level=os.getenv("AGENT_TOOLS_LOG_LEVEL", "INFO"),
        )

    @classmethod
    def _reset(cls) -> None:
        """Clear the lru_cache — used in tests only."""
        cls.load.cache_clear()
