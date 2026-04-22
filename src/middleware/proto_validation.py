"""
ProtoValidationMiddleware — validates execution input and output against
the tool's request/response proto schemas.

This is where the contract promised by ``request.proto`` / ``response.proto``
is actually enforced at call time. Runs on both the request path (before
the handler) and the response path (after).

Request side (strict)
---------------------
* ``ctx.raw_kwargs`` is parsed through ``request.proto`` via
  ``ProtoDescriptor.from_dict``.
* Unknown fields → :class:`ValueError` with the proto ParseError attached.
* Wrong types   → :class:`ValueError`.
* Missing required scalars → protobuf's default-zero fills them, so they
  don't fail validation here (proto-3 semantics). The converter marks them
  required in the LLM schema for guidance only.
* On success, the normalized dict is written to ``ctx.validated_input``
  and the raw :class:`google.protobuf.message.Message` to ``ctx.proto_input``.

Response side (tolerant)
------------------------
* The handler's ``dict`` return value is round-tripped through
  ``response.proto`` with ``ignore_unknown_fields=True``.
* Extra fields in the response are silently **dropped**, not rejected.
  This is important: external APIs (httpbin, GCP services, vendor APIs)
  routinely return more keys than any schema models, and it would be
  painful to update the proto every time a vendor adds a field.
* Type mismatches still raise — if a handler returns ``score: "0.9"``
  where the proto says ``double``, that's a tool bug.

If a tool omits ``request.proto`` / ``response.proto`` entirely, the
corresponding validation step is skipped and the data passes through
untouched.
"""
from __future__ import annotations


class ProtoValidationMiddleware:
    """
    * **Input** — validates ``ctx.raw_kwargs`` against ``request.proto`` before
      handing off to the next middleware.  Sets ``ctx.validated_input`` and
      ``ctx.proto_input``.

    * **Output** — validates the response dict returned by the handler against
      ``response.proto`` before returning to the caller.
    """

    def wrap(self, next_fn):  # type: ignore[no-untyped-def]
        async def _validate(ctx):  # type: ignore[no-untyped-def]
            # ── INPUT ─────────────────────────────────────────────────────────
            if ctx.tool_def.proto_input:
                from google.protobuf.json_format import ParseError

                try:
                    msg = ctx.tool_def.proto_input.from_dict(ctx.raw_kwargs)
                except ParseError as exc:
                    raise ValueError(
                        f"Tool '{ctx.tool_def.name}': invalid input — {exc}"
                    ) from exc
                ctx.validated_input = ctx.tool_def.proto_input.to_dict(msg)
                ctx.proto_input = msg
            else:
                ctx.validated_input = dict(ctx.raw_kwargs)

            # ── EXECUTE ───────────────────────────────────────────────────────
            result = await next_fn(ctx)

            # ── OUTPUT ────────────────────────────────────────────────────────
            # External APIs often return fields we don't model; we keep the
            # fields we DO model and ignore the rest rather than failing.
            if ctx.tool_def.proto_output and isinstance(result, dict):
                from google.protobuf.json_format import ParseError

                try:
                    out_msg = ctx.tool_def.proto_output.from_dict(
                        result, ignore_unknown=True
                    )
                    result = ctx.tool_def.proto_output.to_dict(out_msg)
                except ParseError as exc:
                    raise ValueError(
                        f"Tool '{ctx.tool_def.name}': invalid output — {exc}"
                    ) from exc

            return result

        return _validate
