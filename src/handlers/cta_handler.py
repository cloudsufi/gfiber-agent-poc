"""
CTAHandler — executes Conversational Tooling Agent (Dialogflow CX) tools.

CTA is this framework's name for a Dialogflow CX agent-as-a-tool: the
framework takes a user utterance, sends it as a ``DetectIntent`` request
to the configured CX agent session, and returns the agent's fulfillment
response plus the matched intent and parameters.

Config fields consumed
----------------------
From ``ctx.tool_def.config``:

* ``project_id``       — GCP project hosting the CX agent
* ``location``         — CX region (``global`` or ``us-central1`` etc.)
* ``agent_id``         — the CX agent UUID
* ``language_code``    — BCP-47 lang, defaults to ``en``
* ``text_field``       — which validated-input field carries the utterance
                         (defaults to ``text``)
* ``session_id_field`` — which input field carries the session id; if
                         empty or the field is missing, a fresh uuid4 is
                         generated for a single-turn conversation
* ``api_endpoint``     — optional regional endpoint override
* ``mock_mode``        — when true, skip the network entirely and return
                         a deterministic stub
* ``timeout_seconds``  — per-call timeout override

Credentials
-----------
When ``auth: service_account`` or ``auth: service_agent`` is configured,
:class:`AuthMiddleware` resolves a bearer token into ``ctx.resolved_auth``
and we pass it to the SDK client via a ``StaticBearer`` credential
adapter. Without auth, the SDK falls back to Application Default
Credentials.

Graceful degradation
--------------------
* ``mock_mode: true`` → skip the SDK entirely, return a stub
* SDK not installed (``google-cloud-dialogflowcx``) → log-and-fallback to
  the same stub shape, so an agent demo still runs.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any

from agent_tools.handlers.base import BaseHandler

if TYPE_CHECKING:
    from agent_tools.core.runtime import ExecutionContext

log = logging.getLogger("agent_tools.handlers.cta")


class CTAHandler(BaseHandler):
    async def execute(self, ctx: ExecutionContext) -> Any:
        cfg = ctx.tool_def.config
        inputs = ctx.validated_input

        text_field = cfg.get("text_field", "") or "text"
        session_field = cfg.get("session_id_field", "")

        text = str(inputs.get(text_field, ""))
        if not text:
            raise ValueError(
                f"CTA tool '{ctx.tool_def.name}': no text found in input "
                f"field '{text_field}'. Provide it or change text_field."
            )

        session_id = (
            str(inputs.get(session_field, "")) if session_field else ""
        ) or uuid.uuid4().hex

        if cfg.get("mock_mode"):
            return _mock_response(ctx.tool_def.name, text, session_id, cfg)

        return await _call_dialogflow_cx(
            text=text,
            session_id=session_id,
            cfg=cfg,
            timeout=cfg.get("timeout_seconds") or ctx.tool_def.execution.timeout,
            bearer=ctx.resolved_auth.get("token", ""),
        )


def _mock_response(
    tool_name: str,
    text: str,
    session_id: str,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    """Deterministic stub used when mock_mode is true or the SDK is unavailable."""
    return {
        "session_id": session_id,
        "language_code": cfg.get("language_code", "en"),
        "agent_response": f"[mock cta:{tool_name}] You said: {text}",
        "intent": "mock.echo",
        "confidence": 1.0,
        "parameters": {},
    }


async def _call_dialogflow_cx(
    *,
    text: str,
    session_id: str,
    cfg: dict[str, Any],
    timeout: float | int | None,
    bearer: str,
) -> dict[str, Any]:
    """Hit the real Dialogflow CX agent. Runs on a thread because the SDK is sync."""
    try:
        from google.cloud.dialogflowcx_v3 import (  # type: ignore
            DetectIntentRequest,
            QueryInput,
            SessionsClient,
            TextInput,
        )
    except ImportError:
        log.warning(
            "cta: google-cloud-dialogflowcx not installed — falling back to mock. "
            "Install with: pip install google-cloud-dialogflowcx"
        )
        return _mock_response("unknown", text, session_id, cfg)

    import asyncio

    def _run() -> dict[str, Any]:
        client_opts: dict[str, Any] = {}
        if cfg.get("api_endpoint"):
            client_opts["api_endpoint"] = cfg["api_endpoint"]

        # When the framework already resolved a bearer token (service_account /
        # service_agent auth), pass it in. Otherwise let the SDK use ADC.
        if bearer:
            from google.auth.credentials import Credentials  # type: ignore

            class _StaticBearer(Credentials):
                def __init__(self, token: str) -> None:
                    super().__init__()
                    self.token = token

                def refresh(self, request) -> None:  # noqa: D401, ANN001
                    return None

            client_opts["credentials"] = _StaticBearer(bearer)

        client = SessionsClient(client_options=client_opts if client_opts else None)

        session = (
            f"projects/{cfg['project_id']}/locations/{cfg['location']}"
            f"/agents/{cfg['agent_id']}/sessions/{session_id}"
        )
        request = DetectIntentRequest(
            session=session,
            query_input=QueryInput(
                text=TextInput(text=text),
                language_code=cfg.get("language_code", "en"),
            ),
        )
        resp = client.detect_intent(request=request, timeout=float(timeout or 30))
        result = resp.query_result

        fulfillment = " ".join(
            (m.text.text[0] if m.text and m.text.text else "")
            for m in (result.response_messages or [])
            if m.text
        ).strip()

        intent_name = ""
        confidence = 0.0
        if result.intent:
            intent_name = result.intent.display_name or ""
            confidence = float(result.intent_detection_confidence or 0.0)

        return {
            "session_id": session_id,
            "language_code": result.language_code or cfg.get("language_code", "en"),
            "agent_response": fulfillment,
            "intent": intent_name,
            "confidence": confidence,
            "parameters": dict(result.parameters or {}),
        }

    return await asyncio.to_thread(_run)
