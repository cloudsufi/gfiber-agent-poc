"""
ProtoLoader — compiles ``.proto`` files via ``grpc_tools.protoc`` and returns
:class:`~agent_tools.proto.descriptor.ProtoDescriptor` objects.

This is the one module that deals with protobuf's dynamic-compilation
warts. Everything else in ``agent_tools.proto`` is a thin wrapper over
what comes out of here.

Design notes
------------
* **Per-path caching** — compiled at most once per process (keyed by
  ``Path.resolve()``).  Subsequent ``load()`` calls for the same path
  return the cached :class:`ProtoDescriptor`.
* **Directory co-compilation** — when multiple ``.proto`` files in the
  same directory import one another (e.g. ``api_tool_config.proto`` imports
  ``auth_config.proto``), we compile all of them together into a shared
  output directory so the generated ``*_pb2.py`` siblings can find each
  other at import time. This avoids "No module named auth_config_pb2"
  errors when Python tries to resolve the import.
* **Generic-name collision avoidance** — protobuf's global descriptor
  pool complains loudly if two compiled files have the same logical name.
  Nearly every tool ships a ``request.proto`` and a ``response.proto``,
  so a naive compile would blow up as soon as the second tool loads. We
  sidestep this by renaming generic files to
  ``<parent_dir_name>__<original_name>.proto`` (e.g.
  ``weather_api__request.proto``) before handing them to ``protoc``.
  The rename is only for protoc's book-keeping — the generated message
  class still has the name declared in the proto source.

Failure modes
-------------
* ``grpcio-tools`` missing  → :class:`ImportError` with install hint.
* ``protoc`` exits non-zero → :class:`RuntimeError` with exit code and
  path, nudging the user to check the proto syntax.
"""
from __future__ import annotations

import importlib
import shutil
import sys
import tempfile
from pathlib import Path

from agent_tools.proto.descriptor import ProtoDescriptor

# Names that are generic and will collide across tools if compiled as-is.
_GENERIC_NAMES = {"request.proto", "response.proto"}


class ProtoLoader:
    """
    Synchronous ``.proto`` compiler.  Called at startup from
    :class:`~agent_tools.core.loader.ToolLoader` and
    :class:`~agent_tools.core.config_validator.ConfigValidator`.

    Each file is compiled at most once per process lifetime — subsequent
    ``load()`` calls for the same path return the cached descriptor.
    """

    def __init__(self) -> None:
        self._cache: dict[str, ProtoDescriptor] = {}
        # Shared output dirs keyed by resolved source directory — lets sibling
        # protos (e.g. auth_config_pb2 next to api_tool_config_pb2) find each
        # other at import time.
        self._dir_out: dict[str, str] = {}

    def load(self, proto_path: Path) -> ProtoDescriptor | None:
        """
        Compile *proto_path* and return its :class:`ProtoDescriptor`.

        Returns ``None`` (without raising) if the file does not exist — tools
        may omit ``request.proto`` or ``response.proto``.

        :raises RuntimeError: if ``protoc`` exits with a non-zero status.
        """
        if not proto_path.exists():
            return None

        key = str(proto_path.resolve())
        if key in self._cache:
            return self._cache[key]

        descriptor = self._compile(proto_path, self._dir_out)
        self._cache[key] = descriptor
        return descriptor

    # ── private ───────────────────────────────────────────────────────────────

    @staticmethod
    def _compile(
        proto_path: Path,
        dir_out_cache: dict[str, str] | None = None,
    ) -> ProtoDescriptor:
        try:
            from grpc_tools import protoc
        except ImportError as exc:
            raise ImportError(
                "grpc_tools is required for proto compilation. "
                "Install it with: pip install grpcio-tools"
            ) from exc

        proto_dir = proto_path.parent.resolve()
        dir_key = str(proto_dir)

        # Reuse an existing output dir for this source directory so that
        # all sibling _pb2 modules are co-located.
        if dir_out_cache is not None and dir_key in dir_out_cache:
            out_dir = dir_out_cache[dir_key]
        else:
            out_dir = tempfile.mkdtemp(prefix="agent_tools_proto_")
            if dir_out_cache is not None:
                dir_out_cache[dir_key] = out_dir

        # For generic filenames (request.proto / response.proto) that would
        # collide in protobuf's global descriptor pool when two different tools
        # use the same filename, we compile from a temporary copy that carries
        # the parent directory name as a prefix.
        if proto_path.name in _GENERIC_NAMES:
            descriptor = ProtoLoader._compile_with_unique_name(
                proto_path, out_dir
            )
        else:
            descriptor = ProtoLoader._compile_directory(
                proto_path, proto_dir, out_dir
            )

        return descriptor

    @staticmethod
    def _compile_directory(
        proto_path: Path,
        proto_dir: Path,
        out_dir: str,
    ) -> ProtoDescriptor:
        """Compile all .proto files in *proto_dir* together (handles imports)."""
        from grpc_tools import protoc

        all_protos = sorted(proto_dir.glob("*.proto"))

        ret = protoc.main(
            [
                "grpc_tools.protoc",
                f"--proto_path={proto_dir}",
                f"--python_out={out_dir}",
                *[str(p) for p in all_protos],
            ]
        )
        if ret != 0:
            raise RuntimeError(
                f"protoc failed (exit code {ret}) for {proto_path}. "
                "Check the .proto syntax."
            )

        module_name = f"{proto_path.stem}_pb2"
        return ProtoLoader._import_module(module_name, out_dir, proto_path)

    @staticmethod
    def _compile_with_unique_name(
        proto_path: Path,
        out_dir: str,
    ) -> ProtoDescriptor:
        """
        Compile a generic proto (request.proto / response.proto) under a
        unique name derived from its parent directory to avoid descriptor-pool
        collisions.
        """
        from grpc_tools import protoc

        tool_name = proto_path.parent.name          # e.g. "check_billing"
        unique_stem = f"{tool_name}__{proto_path.stem}"  # "check_billing__request"
        unique_filename = f"{unique_stem}.proto"

        src_dir = tempfile.mkdtemp(prefix="agent_tools_src_")
        try:
            renamed_proto = Path(src_dir) / unique_filename
            renamed_proto.write_text(proto_path.read_text())

            ret = protoc.main(
                [
                    "grpc_tools.protoc",
                    f"--proto_path={src_dir}",
                    f"--python_out={out_dir}",
                    str(renamed_proto),
                ]
            )
            if ret != 0:
                raise RuntimeError(
                    f"protoc failed (exit code {ret}) for {proto_path}. "
                    "Check the .proto syntax."
                )
        finally:
            shutil.rmtree(src_dir, ignore_errors=True)

        module_name = f"{unique_stem}_pb2"
        return ProtoLoader._import_module(module_name, out_dir, proto_path)

    @staticmethod
    def _import_module(
        module_name: str,
        out_dir: str,
        proto_path: Path,
    ) -> ProtoDescriptor:
        """
        Import (or re-import) a ``*_pb2`` module from *out_dir*.

        ``importlib.invalidate_caches()`` is called before the import so
        Python rediscovers ``*_pb2`` files that have been written to an
        ``out_dir`` which was previously added to ``sys.path``. Without this,
        the file finder's negative cache would short-circuit the lookup.
        The old module entry (if any) is popped from ``sys.modules`` so we
        pick up the freshly compiled bytecode rather than a stale one.

        ``sys.path`` is mutated temporarily in a ``try``/``finally`` block
        so the out_dir never permanently pollutes the import path — that
        would eventually break tests that spin up throwaway runtimes.
        """
        sys.path.insert(0, out_dir)
        # Invalidate Python's import caches so newly compiled *_pb2 files
        # are discovered even if this out_dir was previously on sys.path.
        importlib.invalidate_caches()
        try:
            if module_name in sys.modules:
                del sys.modules[module_name]
            module = importlib.import_module(module_name)
        finally:
            sys.path.pop(0)

        return ProtoDescriptor(module=module, proto_path=proto_path)
