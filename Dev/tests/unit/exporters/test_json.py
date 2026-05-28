# SPDX-License-Identifier: Apache-2.0
"""Tests for ``precept.exporters.json_exporter`` (PRC-021).

Covers the JSONL line shape, mode semantics, parent-directory creation,
in-process thread safety, and the no-raise-on-transport-failure
contract for both :class:`JSONFileExporter` and
:class:`JSONStreamExporter`.
"""

from __future__ import annotations

import io
import json
import logging
import threading
from pathlib import Path
from typing import IO
from unittest.mock import patch

import pytest

from precept.evaluator.rules import RuleResult
from precept.exporters.json_exporter import JSONFileExporter, JSONStreamExporter
from precept.scoring.base import ScoreResult
from precept.types import ViolationEvent

_ISO_UTC = "2026-05-23T10:00:00+00:00"


def _make_event(contract_name: str = "x", passed: bool = True) -> ViolationEvent:
    return ViolationEvent(
        contract_name=contract_name,
        contract_version="0.1",
        mode="warn",
        passed=passed,
        score_result=ScoreResult(
            overall_score=1.0 if passed else 0.4,
            field_scores=[],
            scorer_name="stub",
            scorer_version="0.0.1",
            timestamp_iso=_ISO_UTC,
        ),
        rule_results=[RuleResult(rule_name="required_fields", passed=passed)],
        triggered_at_iso=_ISO_UTC,
        source_summary={"a": "1"},
        target_summary={"a": "1"} if passed else {},
    )


# ---------------------------------------------------------------------------
# Name + ABC plumbing
# ---------------------------------------------------------------------------


def test_json_file_exporter_name() -> None:
    assert JSONFileExporter.name == "json_file"


def test_json_stream_exporter_name() -> None:
    assert JSONStreamExporter.name == "json_stream"


# ---------------------------------------------------------------------------
# JSONFileExporter
# ---------------------------------------------------------------------------


def test_json_file_exporter_writes_jsonl_line(tmp_path: Path) -> None:
    out = tmp_path / "events.jsonl"
    exporter = JSONFileExporter(out)
    event = _make_event()
    exporter.export(event)
    contents = out.read_text(encoding="utf-8")
    # Exactly one line, newline-terminated.
    assert contents.endswith("\n")
    assert contents.count("\n") == 1
    parsed = json.loads(contents)
    assert parsed["contract_name"] == "x"
    assert parsed["passed"] is True


def test_json_file_exporter_one_event_per_line(tmp_path: Path) -> None:
    out = tmp_path / "events.jsonl"
    exporter = JSONFileExporter(out)
    events = [_make_event(contract_name=f"c{i}") for i in range(5)]
    for e in events:
        exporter.export(e)
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 5
    parsed = [json.loads(line) for line in lines]
    assert [p["contract_name"] for p in parsed] == [f"c{i}" for i in range(5)]


def test_json_file_exporter_schema_version_present(tmp_path: Path) -> None:
    out = tmp_path / "events.jsonl"
    JSONFileExporter(out).export(_make_event())
    parsed = json.loads(out.read_text(encoding="utf-8"))
    assert parsed["schema_version"] == "0.1"


def test_json_file_exporter_creates_parent_directory(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b" / "c" / "events.jsonl"
    assert not nested.parent.exists()
    JSONFileExporter(nested).export(_make_event())
    assert nested.exists()
    assert nested.parent.is_dir()


def test_json_file_exporter_append_mode_extends_existing_file(tmp_path: Path) -> None:
    out = tmp_path / "events.jsonl"
    out.write_text('{"pre": "existing"}\n', encoding="utf-8")
    JSONFileExporter(out, mode="append").export(_make_event())
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"pre": "existing"}
    assert json.loads(lines[1])["contract_name"] == "x"


def test_json_file_exporter_overwrite_mode_truncates_existing_file(tmp_path: Path) -> None:
    out = tmp_path / "events.jsonl"
    out.write_text('{"pre": "existing"}\n', encoding="utf-8")
    # Truncation happens at construction, before any export call.
    JSONFileExporter(out, mode="overwrite")
    assert out.read_text(encoding="utf-8") == ""


def test_json_file_exporter_overwrite_truncates_then_appends(tmp_path: Path) -> None:
    out = tmp_path / "events.jsonl"
    out.write_text('{"pre": "existing"}\n', encoding="utf-8")
    exp = JSONFileExporter(out, mode="overwrite")
    exp.export(_make_event())
    lines = out.read_text(encoding="utf-8").splitlines()
    # The pre-existing line is gone; only the freshly written event
    # remains.
    assert len(lines) == 1
    assert json.loads(lines[0])["contract_name"] == "x"


def test_json_file_exporter_concurrent_writes_dont_corrupt(tmp_path: Path) -> None:
    """Within a single process, threaded writes must each produce a
    full JSON line with no inter-line interleaving."""

    out = tmp_path / "events.jsonl"
    exporter = JSONFileExporter(out)
    n_threads, per_thread = 8, 25

    def writer(tag: int) -> None:
        for i in range(per_thread):
            exporter.export(_make_event(contract_name=f"t{tag}_e{i}"))

    threads = [threading.Thread(target=writer, args=(t,)) for t in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == n_threads * per_thread
    # Every line is a parseable JSON object with the expected shape.
    for line in lines:
        parsed = json.loads(line)
        assert parsed["contract_version"] == "0.1"
        assert parsed["contract_name"].startswith("t")


def test_json_file_exporter_swallows_oserror(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    out = tmp_path / "events.jsonl"
    exporter = JSONFileExporter(out)
    # Monkey-patch ``Path.open`` to raise OSError on the next call.
    with (
        patch.object(Path, "open", side_effect=OSError("disk full")),
        caplog.at_level(logging.WARNING, logger="precept.exporters.json_exporter"),
    ):
        exporter.export(_make_event())  # must not raise
    joined = " ".join(rec.getMessage() for rec in caplog.records)
    assert "JSONFileExporter" in joined
    assert "disk full" in joined


# ---------------------------------------------------------------------------
# JSONStreamExporter
# ---------------------------------------------------------------------------


def test_json_stream_exporter_writes_to_stringio() -> None:
    stream = io.StringIO()
    JSONStreamExporter(stream).export(_make_event())
    contents = stream.getvalue()
    assert contents.endswith("\n")
    parsed = json.loads(contents)
    assert parsed["contract_name"] == "x"


def test_json_stream_exporter_one_event_per_line() -> None:
    stream = io.StringIO()
    exp = JSONStreamExporter(stream)
    for i in range(3):
        exp.export(_make_event(contract_name=f"c{i}"))
    lines = stream.getvalue().splitlines()
    assert len(lines) == 3


def test_json_stream_exporter_schema_version_present() -> None:
    stream = io.StringIO()
    JSONStreamExporter(stream).export(_make_event())
    parsed = json.loads(stream.getvalue())
    assert parsed["schema_version"] == "0.1"


def test_json_stream_exporter_concurrent_writes_dont_corrupt() -> None:
    stream = io.StringIO()
    exporter = JSONStreamExporter(stream)
    n_threads, per_thread = 6, 20

    def writer(tag: int) -> None:
        for i in range(per_thread):
            exporter.export(_make_event(contract_name=f"t{tag}_e{i}"))

    threads = [threading.Thread(target=writer, args=(t,)) for t in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    lines = stream.getvalue().splitlines()
    assert len(lines) == n_threads * per_thread
    for line in lines:
        parsed = json.loads(line)
        assert parsed["contract_name"].startswith("t")


def test_json_stream_exporter_swallows_valueerror_on_closed_stream(
    caplog: pytest.LogCaptureFixture,
) -> None:
    stream = io.StringIO()
    exporter = JSONStreamExporter(stream)
    stream.close()
    with caplog.at_level(logging.WARNING, logger="precept.exporters.json_exporter"):
        exporter.export(_make_event())  # must not raise
    joined = " ".join(rec.getMessage() for rec in caplog.records)
    assert "JSONStreamExporter" in joined


def test_json_stream_exporter_swallows_oserror(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class _FailingStream:
        def write(self, _: str) -> int:
            raise OSError("broken pipe")

        def flush(self) -> None:  # pragma: no cover -- unreachable after raise
            pass

    stream: IO[str] = _FailingStream()  # type: ignore[assignment]
    exporter = JSONStreamExporter(stream)
    with caplog.at_level(logging.WARNING, logger="precept.exporters.json_exporter"):
        exporter.export(_make_event())  # must not raise
    joined = " ".join(rec.getMessage() for rec in caplog.records)
    assert "broken pipe" in joined
