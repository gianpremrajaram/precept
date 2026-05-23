# SPDX-License-Identifier: MIT
"""Plain JSON exporters: file (JSONL) and arbitrary text stream (PRC-021).

The two concretes are the backup / optionality layer for the OTel
exporter (PRC-020). They write the full :class:`ViolationEvent`
``model_dump(mode='json')`` -- not the 4 KiB-capped compact dict --
because file storage is not size-constrained. Downstream consumers
(the PRC-022 static observatory, log-analysis tools, ``jq`` pipelines)
get the full event detail.

Output format: JSON Lines (one JSON object per line, ``\\n`` separated).
Each line is a fully self-describing event including the top-level
``schema_version`` field already carried by :class:`ViolationEvent`, so
no extra augmentation is needed at the exporter layer.

Thread-safety: both exporters serialise writes within a single process
via :class:`threading.Lock`. **Multi-process** safety (e.g., two
Gunicorn workers writing the same file) is **not** covered at v0 --
``flock``-style cross-process coordination is the application's
responsibility. Documented per-class.

Transport failures (disk full, permission denied, broken pipe) are
logged and swallowed per the :class:`Exporter` contract: an evaluator
call never fails because telemetry is misconfigured.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import IO, ClassVar, Literal

from precept.exporters.base import Exporter
from precept.types import ViolationEvent

__all__ = [
    "JSONFileExporter",
    "JSONStreamExporter",
]


logger = logging.getLogger(__name__)


class JSONFileExporter(Exporter):
    """Append-only JSONL exporter writing one event per line to a file.

    Construction creates the parent directory if missing and, in
    ``mode="overwrite"``, truncates the destination file. The file is
    re-opened in append mode for each :meth:`export` call (no idle
    handle), which keeps the surface friendly to log-rotation tools
    and reduces the cost of a misbehaving evaluator.

    Thread-safe within a single process: a :class:`threading.Lock`
    serialises writes so concurrent evaluators do not interleave bytes
    within a line. **Multi-process** safety (two workers writing the
    same file) is not covered at v0 -- use an external coordination
    primitive (e.g. ``fcntl.flock``) or per-worker output paths if you
    need that property.
    """

    name: ClassVar[str] = "json_file"

    def __init__(
        self,
        path: str | Path,
        mode: Literal["append", "overwrite"] = "append",
    ) -> None:
        self._path: Path = Path(path)
        self._mode: Literal["append", "overwrite"] = mode
        self._lock: threading.Lock = threading.Lock()

        # Create the parent directory eagerly so a missing-directory
        # configuration error surfaces at application startup rather
        # than on the first handoff. mkdir(parents=True, exist_ok=True)
        # is idempotent on the typical "directory already exists" case.
        self._path.parent.mkdir(parents=True, exist_ok=True)

        # Truncate the destination eagerly on overwrite so the file is
        # in a known state before any evaluation runs. We do not hold
        # the handle open afterwards -- each export() re-opens in
        # append mode, which gives log-rotation tools a clean
        # truncate-and-recreate path.
        if self._mode == "overwrite":
            try:
                with self._path.open("w", encoding="utf-8"):
                    pass
            except OSError as exc:
                logger.warning(
                    "JSONFileExporter: failed to truncate %s on construction: %s",
                    self._path,
                    exc,
                )

    def export(self, event: ViolationEvent) -> None:
        line = json.dumps(event.model_dump(mode="json"), ensure_ascii=False) + "\n"
        with self._lock:
            try:
                with self._path.open("a", encoding="utf-8") as fh:
                    fh.write(line)
                    fh.flush()
            except OSError as exc:
                # Per Exporter contract: never raise on transport
                # failure. Disk full, permission denied, broken
                # filesystem all surface here.
                logger.warning(
                    "JSONFileExporter: write to %s failed: %s",
                    self._path,
                    exc,
                )


class JSONStreamExporter(Exporter):
    """JSONL exporter writing to any writable text stream.

    Unlike :class:`JSONFileExporter`, this exporter holds the supplied
    stream by reference -- it does not open, close, or otherwise
    manage the stream's lifecycle. The caller is responsible for
    flushing (we flush after each write anyway) and for closing the
    stream when finished. Use for ``sys.stdout``, in-memory
    :class:`io.StringIO`, or any custom writable text stream.

    Thread-safe within a single process (:class:`threading.Lock`).
    Multi-process safety is the caller's problem -- by definition
    a shared stream object cannot be passed across processes.
    """

    name: ClassVar[str] = "json_stream"

    def __init__(self, stream: IO[str]) -> None:
        self._stream: IO[str] = stream
        self._lock: threading.Lock = threading.Lock()

    def export(self, event: ViolationEvent) -> None:
        line = json.dumps(event.model_dump(mode="json"), ensure_ascii=False) + "\n"
        with self._lock:
            try:
                self._stream.write(line)
                self._stream.flush()
            # OSError covers disk-backed streams; ValueError covers
            # writes to closed streams; broader Exception kept off the
            # table per CLAUDE.md "Error handling".
            except (OSError, ValueError) as exc:
                logger.warning(
                    "JSONStreamExporter: write failed: %s",
                    exc,
                )
