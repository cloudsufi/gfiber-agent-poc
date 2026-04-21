"""
ProtoValidationMiddleware — validates execution input and output against
the tool's request/response proto schemas.
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
            if ctx.tool_def.proto_output and isinstance(result, dict):
                from google.protobuf.json_format import ParseError

                try:
                    out_msg = ctx.tool_def.proto_output.from_dict(result)
                    result = ctx.tool_def.proto_output.to_dict(out_msg)
                except ParseError as exc:
                    raise ValueError(
                        f"Tool '{ctx.tool_def.name}': invalid output — {exc}"
                    ) from exc

            return result

        return _validate
