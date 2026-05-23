# SPDX-License-Identifier: MIT
"""Subprocess-driven integration tests for the PRC-019 demo runner.

Exercises ``examples/demo.py`` exactly as a reviewer would: invokes it
through ``sys.executable`` (so the demo runs in the same venv as the
test) and asserts the AC contract on the resulting exit code, stdout
summary, and output JSON.

Each ``subprocess.run`` spins up a fresh Python process and loads its
own ~150 MB ``EmbeddingProxy`` weights, so the per-trace invocations are
hoisted into module-scoped fixtures and shared across tests that read
the same artefact. Three invocations cover the full positive matrix
(clean, degraded, degraded-repeat for the determinism check); a fourth
covers the runtime-error path and fails before model load. Subprocess
timeout is 120 s -- the PRC-019 AC target is <30 s and this leaves
ample headroom for a cold cache on a slow CI runner.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEMO_PATH = _REPO_ROOT / "examples" / "demo.py"

_SUBPROCESS_TIMEOUT_SECS = 120


def _run_demo(
    *,
    trace: str,
    output: Path,
    extra_args: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Invoke ``examples/demo.py`` and return the completed process record.

    Always passes ``--no-color`` (subprocesses do not have a TTY in
    pytest anyway, but the explicit flag makes the assertion targets
    free of ANSI escapes regardless of harness changes).
    """
    cmd = [
        sys.executable,
        str(_DEMO_PATH),
        "--trace",
        trace,
        "--output",
        str(output),
        "--no-color",
    ]
    if extra_args:
        cmd.extend(extra_args)
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=_SUBPROCESS_TIMEOUT_SECS,
        check=False,
    )


@pytest.fixture(scope="module")
def demo_clean(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[subprocess.CompletedProcess[str], Path, dict[str, Any]]:
    output = tmp_path_factory.mktemp("demo_clean") / "demo_trace.json"
    result = _run_demo(trace="clean", output=output)
    assert output.is_file(), (
        f"clean demo did not write {output}; stdout=\n{result.stdout}\nstderr=\n{result.stderr}"
    )
    parsed = json.loads(output.read_text(encoding="utf-8"))
    return result, output, parsed


@pytest.fixture(scope="module")
def demo_degraded(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[subprocess.CompletedProcess[str], Path, dict[str, Any]]:
    output = tmp_path_factory.mktemp("demo_degraded") / "demo_trace.json"
    result = _run_demo(trace="degraded", output=output)
    assert output.is_file(), (
        f"degraded demo did not write {output}; stdout=\n{result.stdout}\nstderr=\n{result.stderr}"
    )
    parsed = json.loads(output.read_text(encoding="utf-8"))
    return result, output, parsed


def test_demo_clean_exits_zero(
    demo_clean: tuple[subprocess.CompletedProcess[str], Path, dict[str, Any]],
) -> None:
    result, _, _ = demo_clean
    assert result.returncode == 0, (
        f"clean trace must exit 0; got {result.returncode}\n"
        f"stdout=\n{result.stdout}\nstderr=\n{result.stderr}"
    )


def test_demo_degraded_exits_zero(
    demo_degraded: tuple[subprocess.CompletedProcess[str], Path, dict[str, Any]],
) -> None:
    """PRC-019 AC: violations do NOT change the exit code (regression catcher).

    A reviewer typing ``python examples/demo.py`` should never see exit
    code 1; a non-zero exit means the demo crashed, not that a contract
    fired.
    """
    result, _, _ = demo_degraded
    assert result.returncode == 0, (
        f"degraded trace must exit 0 even with violations; got {result.returncode}\n"
        f"stdout=\n{result.stdout}\nstderr=\n{result.stderr}"
    )


def test_demo_clean_no_violations(
    demo_clean: tuple[subprocess.CompletedProcess[str], Path, dict[str, Any]],
) -> None:
    _, _, parsed = demo_clean
    for hop in parsed["hops"]:
        assert hop["violation_event"]["passed"] is True, (
            f"clean trace produced a violation at hop "
            f"{hop['handoff_metadata']['source_agent']}->"
            f"{hop['handoff_metadata']['target_agent']}: "
            f"rules={hop['violation_event']['rule_results']}"
        )
        assert hop["impact_summary"] is None


def test_demo_degraded_fails_only_at_summariser_to_writer(
    demo_degraded: tuple[subprocess.CompletedProcess[str], Path, dict[str, Any]],
) -> None:
    _, _, parsed = demo_degraded
    hops = parsed["hops"]
    assert len(hops) == 2

    researcher_hop, summariser_hop = hops
    assert researcher_hop["violation_event"]["passed"] is True
    assert summariser_hop["violation_event"]["passed"] is False
    assert summariser_hop["violation_event"]["contract_name"] == "summariser_to_writer"

    failing = sorted(
        r["rule_name"] for r in summariser_hop["violation_event"]["rule_results"] if not r["passed"]
    )
    assert failing == ["forbidden_drops", "preserved_entities"], (
        f"degraded summariser->writer must fail exactly forbidden_drops + "
        f"preserved_entities; got {failing!r}"
    )


def test_demo_degraded_bakes_impact_summary(
    demo_degraded: tuple[subprocess.CompletedProcess[str], Path, dict[str, Any]],
) -> None:
    """PRC-022 coordination: the observatory loads ``impact_summary`` directly."""
    _, _, parsed = demo_degraded
    failed_hop = parsed["hops"][1]
    impact = failed_hop["impact_summary"]
    assert isinstance(impact, str) and impact, (
        "failed hop must carry a non-empty impact_summary for the observatory"
    )
    # Confirm the curated PRC-015 template fired (preserved_entities is the
    # first failing rule in evaluator order required_fields -> preserved_entities
    # -> forbidden_drops).
    assert "Primary sources may be dropped" in impact, (
        f"impact summary missing the curated preserved_entities template: {impact!r}"
    )
    assert "summariser to writer blocked" in impact, (
        f"impact summary should name the source/target agents from handoff_metadata: {impact!r}"
    )


def test_demo_summary_line_clean(
    demo_clean: tuple[subprocess.CompletedProcess[str], Path, dict[str, Any]],
) -> None:
    result, _, _ = demo_clean
    assert "DEMO COMPLETED (no violations)" in result.stdout, (
        f"clean run missing summary line; stdout=\n{result.stdout}"
    )


def test_demo_summary_line_degraded(
    demo_degraded: tuple[subprocess.CompletedProcess[str], Path, dict[str, Any]],
) -> None:
    result, _, _ = demo_degraded
    assert "DEMO COMPLETED (1 violation detected)" in result.stdout, (
        f"degraded run missing summary line; stdout=\n{result.stdout}"
    )


def test_demo_output_pointer_present(
    demo_degraded: tuple[subprocess.CompletedProcess[str], Path, dict[str, Any]],
) -> None:
    """PRC-019 AC: console output must point reviewers at the observatory."""
    result, _, _ = demo_degraded
    assert "docs/index.html" in result.stdout
    assert "examples/output/demo_trace.json" in result.stdout


def test_demo_output_json_shape(
    demo_degraded: tuple[subprocess.CompletedProcess[str], Path, dict[str, Any]],
) -> None:
    _, _, parsed = demo_degraded
    assert set(parsed) == {
        "schema_version",
        "precept_version",
        "trace_name",
        "generated_at_iso",
        "hops",
    }
    assert parsed["schema_version"] == "0.1"
    assert parsed["trace_name"] == "degraded"
    assert parsed["generated_at_iso"], "generated_at_iso must be a non-empty stable timestamp"
    for hop in parsed["hops"]:
        assert set(hop) == {
            "handoff_metadata",
            "source_payload",
            "target_payload",
            "violation_event",
            "impact_summary",
        }
        assert set(hop["handoff_metadata"]) == {
            "source_agent",
            "target_agent",
            "contract_name",
            "timestamp_iso",
        }


def test_demo_output_json_human_readable_format(
    demo_degraded: tuple[subprocess.CompletedProcess[str], Path, dict[str, Any]],
) -> None:
    """PRC-019 AC: ``json.dump(..., indent=2, sort_keys=True)``.

    Round-tripping the raw file through the same dump options must
    produce the same bytes (modulo the trailing newline we already
    write). Catches: indent regression, sort_keys regression, and any
    silent reorder of the output writer.
    """
    _, output_path, parsed = demo_degraded
    raw = output_path.read_text(encoding="utf-8")
    redumped = json.dumps(parsed, indent=2, sort_keys=True) + "\n"
    assert raw == redumped


def test_demo_deterministic_on_repeat(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """PRC-019 AC: two runs of the same trace produce byte-identical JSON."""
    out_a = tmp_path_factory.mktemp("demo_det_a") / "demo_trace.json"
    out_b = tmp_path_factory.mktemp("demo_det_b") / "demo_trace.json"
    r_a = _run_demo(trace="degraded", output=out_a)
    r_b = _run_demo(trace="degraded", output=out_b)
    assert r_a.returncode == 0
    assert r_b.returncode == 0
    bytes_a = out_a.read_bytes()
    bytes_b = out_b.read_bytes()
    assert bytes_a == bytes_b, (
        "two degraded runs produced different output JSON; "
        "check event_id / triggered_at_iso / score_result.timestamp_iso "
        "are being overwritten with stable values"
    )


def test_demo_runtime_error_exits_two(tmp_path: Path) -> None:
    """PRC-019 AC: a runtime error (here: missing fixtures dir) exits 2, not 1.

    Pointing ``--fixtures-dir`` at a nonexistent directory makes the
    fixture read fail; ``main`` must translate the exception to exit
    code 2 with a ``DEMO FAILED`` line on stderr -- never a traceback,
    never exit code 1.
    """
    missing = tmp_path / "no-such-fixtures-dir"
    assert not missing.exists()
    output = tmp_path / "should-not-be-written.json"
    result = _run_demo(
        trace="clean",
        output=output,
        extra_args=["--fixtures-dir", str(missing)],
    )
    assert result.returncode == 2, (
        f"runtime error must exit 2; got {result.returncode}\n"
        f"stdout=\n{result.stdout}\nstderr=\n{result.stderr}"
    )
    assert "DEMO FAILED" in result.stderr, (
        f"runtime error must print 'DEMO FAILED' on stderr; stderr=\n{result.stderr}"
    )
