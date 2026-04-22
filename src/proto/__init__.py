"""
agent_tools.proto — protobuf integration layer.

The framework is proto-first: every tool's config, input, and output is
described by a ``.proto`` file. This subpackage hides the ergonomically
rough edges of protobuf (dynamic compilation, descriptor-pool collisions,
scalar-to-JSON-Schema mapping) behind three focused classes.

Components
----------
* :class:`~agent_tools.proto.loader.ProtoLoader` — compiles ``.proto``
  source to an in-memory ``_pb2`` module using ``grpc_tools.protoc``.
  Caches per absolute path; compiles sibling files in the same directory
  together so ``import "auth_config.proto"`` resolves correctly.

* :class:`~agent_tools.proto.descriptor.ProtoDescriptor` — typed wrapper
  around the compiled module. Exposes the primary message class and
  ``from_dict`` / ``to_dict`` helpers backed by ``google.protobuf.json_format``.

* :class:`~agent_tools.proto.converter.ProtoSchemaConverter` — converts a
  descriptor into the JSON Schema dict that ADK / LLM frameworks require
  for tool declarations. Proto-3 scalar types are mapped to JSON primitives;
  nested messages recurse; non-message scalar fields at the root are marked
  ``required`` to give the LLM clearer guidance.

Why the indirection?
~~~~~~~~~~~~~~~~~~~~
protobuf's default global descriptor pool refuses two files with the same
logical name. Several tools declare their own ``request.proto`` and
``response.proto`` in their own directories — which would collide on import.
:class:`ProtoLoader` copies those "generic" filenames to a per-tool unique
name (``<tool>__request.proto``) before compiling, so every tool's schema
lives in its own descriptor. This is the one subtlety the rest of the
framework relies on; everything else here is mechanical wrapping around
``google.protobuf``.
"""
