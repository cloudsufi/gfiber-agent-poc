"""
agent_tools.schema — YAML / JSON-Schema integration layer.

The framework is schema-first: every tool's config, input, and output is
described by a YAML file whose contents are valid JSON Schema. This
subpackage wraps :mod:`jsonschema` to provide:

* :func:`~agent_tools.schema.loader.load_schema` — read a YAML schema file.
* :func:`~agent_tools.schema.validator.validate_input` — strict validation,
  rejects unknown fields and wrong types.
* :func:`~agent_tools.schema.validator.validate_output` — lenient validation
  that keeps declared-and-typed fields and silently drops extras (external
  APIs tend to return more keys than we model).
* :func:`~agent_tools.schema.converter.to_llm_schema` — strips metadata
  fields (``$schema``, ``title``) so the bare schema can be attached to an
  ADK / LLM tool declaration.

Why JSON Schema (as YAML) over protobuf
---------------------------------------
* Zero build step — YAML loads at startup, no protoc compilation.
* Zero binary deps — ``jsonschema`` is pure Python.
* Human-writeable — tool authors can edit schemas without understanding
  protobuf conventions.
* Same output format — the schema we use to validate is already the schema
  LLMs / ADK expect, so there's no conversion layer.
"""
