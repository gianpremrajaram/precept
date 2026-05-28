# SPDX-License-Identifier: Apache-2.0
"""Tests for ``precept.exporters.otel`` (PRC-020).

Covers the import-guard surface (module-level import + stub
instantiation when ``opentelemetry`` is absent), the attribute
construction (GenAI canonical names, content-capture env gate,
per-attribute size backstop), and the two emission paths (current
recording span and synthetic ``invoke_agent`` span).

``opentelemetry`` is required for most tests in this file; the file
imports it unconditionally because the venv used by CI installs
``[otel]`` for the test job's coverage of the integration path. The
absent-OTel path is exercised via subprocess (so the parent test
process can keep OTel installed).
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import textwrap
from typing import Any

import pytest

# These imports require ``[otel]``; skip the entire module if not
# present so the unit-test job stays green on base installs. The
# subprocess-driven import-guard tests below do not depend on this
# import succeeding.
opentelemetry = pytest.importorskip("opentelemetry")
from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (  # noqa: E402
    InMemorySpanExporter,
)

from precept.evaluator.rules import RuleResult  # noqa: E402
from precept.exporters.otel import (  # noqa: E402
    OTelExporter,
    _build_attributes,
    _truncate_utf8,
)
from precept.scoring.base import FieldScore, ScoreResult  # noqa: E402
from precept.types import ViolationEvent  # noqa: E402

_ISO_UTC = "2026-05-23T10:00:00+00:00"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_event(
    *,
    passed: bool = True,
    contract_name: str = "demo_contract",
    rule_message: str | None = None,
    field_scores: list[FieldScore] | None = None,
    source_summary: dict[str, str] | None = None,
    target_summary: dict[str, str] | None = None,
) -> ViolationEvent:
    return ViolationEvent(
        contract_name=contract_name,
        contract_version="0.1",
        mode="warn",
        passed=passed,
        score_result=ScoreResult(
            overall_score=1.0 if passed else 0.4,
            field_scores=field_scores if field_scores is not None else [],
            scorer_name="stub",
            scorer_version="0.0.1",
            timestamp_iso=_ISO_UTC,
        ),
        rule_results=[
            RuleResult(
                rule_name="required_fields",
                passed=passed,
                violation_message=rule_message,
            )
        ],
        triggered_at_iso=_ISO_UTC,
        source_summary=source_summary if source_summary is not None else {"a": "alpha"},
        target_summary=target_summary if target_summary is not None else {"a": "alpha"},
    )


@pytest.fixture
def in_memory_provider() -> tuple[TracerProvider, InMemorySpanExporter]:
    """Configured TracerProvider with InMemorySpanExporter.

    NOT registered as the global provider (so other tests are
    unaffected); the caller passes ``provider.get_tracer(...)`` into
    OTelExporter directly.
    """
    provider = TracerProvider()
    memory = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(memory))
    return provider, memory


@pytest.fixture(autouse=True)
def _isolate_content_capture_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure each test starts from a known content-capture state."""
    monkeypatch.delenv("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", raising=False)
    monkeypatch.delenv("OTEL_SEMCONV_STABILITY_OPT_IN", raising=False)


# ---------------------------------------------------------------------------
# Name + ABC plumbing
# ---------------------------------------------------------------------------


def test_otel_exporter_name() -> None:
    assert OTelExporter.name == "otel"


def test_otel_exporter_default_tracer_is_proxy() -> None:
    exp = OTelExporter()
    # With OTel installed but no global SDK configured, the API
    # returns a ProxyTracer that defers to whichever provider is set.
    assert exp._tracer is not None


def test_otel_exporter_accepts_explicit_tracer(
    in_memory_provider: tuple[TracerProvider, InMemorySpanExporter],
) -> None:
    provider, _ = in_memory_provider
    tracer = provider.get_tracer("precept-test")
    exp = OTelExporter(tracer=tracer)
    assert exp._tracer is tracer


# ---------------------------------------------------------------------------
# _build_attributes
# ---------------------------------------------------------------------------


def test_build_attributes_includes_genai_canonical_keys() -> None:
    event = _make_event(passed=False, rule_message="required field 'x' missing")
    attrs = _build_attributes(event)
    assert attrs["gen_ai.evaluation.name"] == "demo_contract"
    assert attrs["gen_ai.evaluation.score.value"] == event.score_result.overall_score
    assert attrs["gen_ai.evaluation.score.label"] == "failed"
    assert "required field 'x' missing" in attrs["gen_ai.evaluation.explanation"]


def test_build_attributes_passed_label_and_empty_explanation() -> None:
    event = _make_event(passed=True)
    attrs = _build_attributes(event)
    assert attrs["gen_ai.evaluation.score.label"] == "passed"
    assert attrs["gen_ai.evaluation.explanation"] == ""


def test_build_attributes_explanation_fallback_for_pure_score_gate() -> None:
    # Score-gate failure (FieldScore.passed=False) with no rule
    # producing a violation_message: the explanation should fall back
    # to the documented generic string.
    event = _make_event(
        passed=False,
        rule_message=None,
        field_scores=[
            FieldScore(field_name="x", score=0.1, method="embedding_cosine", passed=False),
        ],
    )
    attrs = _build_attributes(event)
    assert "evaluation failed" in attrs["gen_ai.evaluation.explanation"]


def test_build_attributes_drops_content_by_default() -> None:
    event = _make_event(
        source_summary={"hypothesis": "secret-source-content"},
        target_summary={"hypothesis": "secret-target-content"},
    )
    attrs = _build_attributes(event)
    for k in attrs:
        assert not k.startswith("precept.source."), k
        assert not k.startswith("precept.target."), k


def test_build_attributes_includes_content_when_env_var_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "True")
    event = _make_event(
        source_summary={"hypothesis": "source-content"},
        target_summary={"hypothesis": "target-content"},
    )
    attrs = _build_attributes(event)
    assert attrs["precept.source.hypothesis"] == "source-content"
    assert attrs["precept.target.hypothesis"] == "target-content"


def test_build_attributes_content_capture_env_var_is_case_insensitive_on_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "true")
    event = _make_event(source_summary={"a": "x"}, target_summary={"a": "x"})
    attrs = _build_attributes(event)
    assert "precept.source.a" in attrs


def test_build_attributes_propagates_payload_truncated_flag() -> None:
    # Synthetically inflate the source summary so to_compact_dict()
    # truncates it and sets the flag. Use a large set of distinct keys
    # so the JSON serialisation crosses 4 KiB.
    big_source = {f"field_{i}": "x" * 100 for i in range(60)}
    event = _make_event(source_summary=big_source, target_summary=big_source)
    attrs = _build_attributes(event)
    # The compact-dict truncation marker is preserved even though
    # content capture is OFF (so the source/target keys are dropped
    # afterwards). The flag itself is metadata, not content.
    assert attrs.get("precept.payload_truncated") is True


def test_build_attributes_per_attribute_truncation_via_explanation() -> None:
    # The realistic path into the per-attribute backstop is via
    # ``gen_ai.evaluation.explanation``: it is built from
    # ``violation_message`` strings which are NOT pre-capped by
    # ``to_compact_dict``. A pathological multi-kilobyte rule message
    # produces an oversize explanation; the backstop truncates it.
    huge_msg = "x" * (4096 + 200)
    event = _make_event(passed=False, rule_message=huge_msg)
    attrs = _build_attributes(event)
    explanation = attrs["gen_ai.evaluation.explanation"]
    assert isinstance(explanation, str)
    assert explanation.endswith("...[truncated]")
    assert len(explanation.encode("utf-8")) <= 4096


def test_truncate_utf8_helper_bytes_under_limit() -> None:
    # Unit-level coverage of the byte-aware truncation helper.
    huge = "x" * (4096 + 200)
    truncated = _truncate_utf8(huge, 4096)
    assert truncated.endswith("...[truncated]")
    assert len(truncated.encode("utf-8")) <= 4096


def test_truncate_utf8_helper_handles_multibyte_boundary() -> None:
    # A multi-byte character straddling the byte slice must not raise;
    # ``errors="ignore"`` on decode handles it cleanly.
    # ``é`` is two UTF-8 bytes; ensure the helper does not produce
    # garbled output when the slice cuts mid-character.
    payload = "é" * 3000  # 6000 bytes total
    truncated = _truncate_utf8(payload, 4096)
    assert truncated.endswith("...[truncated]")
    assert len(truncated.encode("utf-8")) <= 4096


# ---------------------------------------------------------------------------
# Emission paths (current span vs synthetic invoke_agent span)
# ---------------------------------------------------------------------------


def test_export_attaches_event_to_current_recording_span(
    in_memory_provider: tuple[TracerProvider, InMemorySpanExporter],
) -> None:
    provider, memory = in_memory_provider
    tracer = provider.get_tracer("precept-test")
    exp = OTelExporter(tracer=tracer)
    event = _make_event(passed=False, rule_message="required missing")

    with tracer.start_as_current_span("agent-call") as parent:
        assert parent.is_recording()
        exp.export(event)

    finished = memory.get_finished_spans()
    # Only the parent span was created/ended; no synthetic span.
    assert len(finished) == 1
    parent_span = finished[0]
    assert parent_span.name == "agent-call"
    # The gen_ai.evaluation.result event landed on the parent.
    event_names = [e.name for e in parent_span.events]
    assert "gen_ai.evaluation.result" in event_names
    captured = next(e for e in parent_span.events if e.name == "gen_ai.evaluation.result")
    assert captured.attributes is not None
    assert captured.attributes["gen_ai.evaluation.score.label"] == "failed"


def test_export_opens_synthetic_invoke_agent_span_when_no_current_span(
    in_memory_provider: tuple[TracerProvider, InMemorySpanExporter],
) -> None:
    provider, memory = in_memory_provider
    tracer = provider.get_tracer("precept-test")
    exp = OTelExporter(tracer=tracer)
    event = _make_event()

    # No active span on entry. The exporter must open a synthetic
    # ``invoke_agent`` span.
    exp.export(event)

    finished = memory.get_finished_spans()
    assert len(finished) == 1
    synth = finished[0]
    assert synth.name == "invoke_agent"
    event_names = [e.name for e in synth.events]
    assert "gen_ai.evaluation.result" in event_names


def test_export_resilient_when_no_sdk_configured(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When no global SDK is configured (ProxyTracer / NoOp), export
    must not raise; the dropped-event misconfiguration is logged at
    DEBUG."""
    exp = OTelExporter()  # default tracer = global ProxyTracer
    with caplog.at_level(logging.DEBUG, logger="precept.exporters.otel"):
        exp.export(_make_event())  # must not raise
    joined = " ".join(rec.getMessage() for rec in caplog.records)
    assert "no OTel SDK configured" in joined


def test_export_swallows_tracer_exceptions(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class _ExplodingTracer:
        def start_as_current_span(self, *args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("tracer broke")

    exp = OTelExporter(tracer=_ExplodingTracer())  # type: ignore[arg-type]
    with caplog.at_level(logging.DEBUG, logger="precept.exporters.otel"):
        exp.export(_make_event())  # must not raise
    joined = " ".join(rec.getMessage() for rec in caplog.records)
    assert "export failed" in joined
    assert "tracer broke" in joined


def test_export_logs_stability_opt_in_when_set(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    in_memory_provider: tuple[TracerProvider, InMemorySpanExporter],
) -> None:
    monkeypatch.setenv("OTEL_SEMCONV_STABILITY_OPT_IN", "gen_ai_latest_experimental")
    provider, _ = in_memory_provider
    tracer = provider.get_tracer("precept-test")
    exp = OTelExporter(tracer=tracer)
    with caplog.at_level(logging.DEBUG, logger="precept.exporters.otel"):
        exp.export(_make_event())
    joined = " ".join(rec.getMessage() for rec in caplog.records)
    assert "OTEL_SEMCONV_STABILITY_OPT_IN" in joined
    assert "gen_ai_latest_experimental" in joined


# ---------------------------------------------------------------------------
# EventLogger experimental path (opt-in via constructor)
# ---------------------------------------------------------------------------


def test_export_prefers_event_logger_when_supplied(
    in_memory_provider: tuple[TracerProvider, InMemorySpanExporter],
) -> None:
    provider, memory = in_memory_provider
    tracer = provider.get_tracer("precept-test")

    captured: list[Any] = []

    class _CapturingEventLogger:
        def emit(self, event: Any) -> None:
            captured.append(event)

    exp = OTelExporter(
        tracer=tracer,
        event_logger=_CapturingEventLogger(),  # type: ignore[arg-type]
    )
    exp.export(_make_event())

    # event_logger path used; no spans created.
    assert len(captured) == 1
    # ``get_finished_spans()`` returns a tuple in the installed
    # opentelemetry-sdk; coerce to a length check rather than
    # comparing against a list literal.
    assert len(memory.get_finished_spans()) == 0
    emitted = captured[0]
    assert emitted.name == "gen_ai.evaluation.result"
    assert emitted.attributes["gen_ai.evaluation.name"] == "demo_contract"


# ---------------------------------------------------------------------------
# Import-guard surface (subprocess-driven)
# ---------------------------------------------------------------------------


_ABSENT_OTEL_PROBE = textwrap.dedent(
    """
    import sys

    # Block any import beginning with ``opentelemetry`` so the next
    # ``import precept.exporters.otel`` resolves the ImportError
    # branch of the module-level guard.
    blocked = {name: None for name in list(sys.modules) if name.startswith("opentelemetry")}
    sys.modules.update(blocked)
    sys.modules["opentelemetry"] = None
    sys.modules["opentelemetry.trace"] = None

    # Drop any pre-imported precept.exporters.otel so the module
    # re-executes with the blocked imports in place.
    for name in list(sys.modules):
        if name == "precept.exporters.otel":
            del sys.modules[name]

    import precept.exporters.otel as otel_mod

    # Module-level import must succeed.
    assert otel_mod.OTelExporter is not None, "OTelExporter not defined"
    assert otel_mod.OTelExporter.name == "otel"

    # Construction must raise ImportError with the install hint.
    try:
        otel_mod.OTelExporter()
    except ImportError as exc:
        assert "precept[otel]" in str(exc), str(exc)
    else:
        raise AssertionError("OTelExporter() did not raise ImportError on absent SDK")

    # export() on the stub must also raise ImportError, even when
    # someone bypasses __init__ via __new__ (defensive backstop).
    stub_instance = otel_mod.OTelExporter.__new__(otel_mod.OTelExporter)
    try:
        stub_instance.export(None)
    except ImportError as exc:
        assert "precept[otel]" in str(exc), str(exc)
    else:
        raise AssertionError("stub export() did not raise ImportError")

    print("PASS")
    """
)


def test_module_imports_and_stub_raises_when_otel_absent(tmp_path: Any) -> None:
    """In a child Python process, block ``opentelemetry`` and assert
    that ``import precept.exporters.otel`` still succeeds, while
    construction + ``export`` raise ImportError with the install hint."""
    script = tmp_path / "probe.py"
    script.write_text(_ABSENT_OTEL_PROBE)
    # Inherit our env so PYTHONPATH / venv resolution stays consistent.
    env = dict(os.environ)
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, (
        f"probe failed: stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "PASS" in result.stdout, result.stdout
