"""
SchemaValidationMiddleware — validates execution input and output against
the tool's YAML / JSON Schema.

Runs on both the request path (before the handler) and the response path
(after). This is where the contract promised by ``input.yaml`` /
``output.yaml`` is enforced at call time.

Request side (strict)
---------------------
* ``ctx.raw_kwargs`` is validated against ``ctx.tool_def.input_schema``
  via :func:`validate_input`. Schemas that declare
  ``additionalProperties: false`` (the convention for this framework's
  input schemas) reject unknown fields. Missing required fields raise.
* The validated dict is written to ``ctx.validated_input`` and handlers
  read from there — not from ``raw_kwargs``.

Response side (lenient)
-----------------------
* The handler's dict return is run through :func:`validate_output`, which
  keeps only declared top-level fields before running the validator.
  External APIs (httpbin, GCP services, vendor APIs) often return more
  keys than we model, and the lenient path means we don't need to update
  a schema every time a vendor adds a field.
* Declared fields that fail type / enum / format validation still raise —
  a tool returning ``score: "0.9"`` where the schema says ``number`` is
  a tool bug and should fail loudly.

When a tool omits the corresponding schema entirely, the validation step
is skipped and the data passes through untouched.
"""

from __future__ import annotations


class SchemaValidationMiddleware:
    def wrap(self, next_fn):  # type: ignore[no-untyped-def]
        from agent_tools.schema.validator import validate_input, validate_output

        async def _validate(ctx):  # type: ignore[no-untyped-def]
            # ── INPUT ─────────────────────────────────────────────────────────
            if ctx.tool_def.input_schema:
                try:
                    ctx.validated_input = validate_input(ctx.raw_kwargs, ctx.tool_def.input_schema)
                except ValueError as exc:
                    raise ValueError(f"Tool '{ctx.tool_def.name}': invalid input — {exc}") from exc
            else:
                ctx.validated_input = dict(ctx.raw_kwargs)

            # ── EXECUTE ───────────────────────────────────────────────────────
            result = await next_fn(ctx)

            # ── OUTPUT ────────────────────────────────────────────────────────
            if ctx.tool_def.output_schema and isinstance(result, dict):
                try:
                    result = validate_output(result, ctx.tool_def.output_schema)
                except ValueError as exc:
                    raise ValueError(f"Tool '{ctx.tool_def.name}': invalid output — {exc}") from exc

            return result

        return _validate
