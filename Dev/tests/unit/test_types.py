# SPDX-License-Identifier: MIT
"""Tests for ``precept.types.ViolationEvent`` (PRC-013).

Covers the required fields, the timestamp validator (parity with
``ScoreResult._validate_timestamp_iso_utc``), and the
``to_compact_dict`` 4 KiB ceiling with target-then-source truncation.

Includes a schema-drift canary so any future addition/removal/rename
of a ``ViolationEvent`` field surfaces immediately rather than silently
breaking the OTel-attribute layout.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from precept.evaluator.rules import RuleResult
from precept.scoring.base import FieldScore, ScoreResult
from precept.types import ViolationEvent

_ISO_UTC = "2026-05-10T22:51:00+00:00"


def _score_result(field_scores: list[FieldScore] | None = None) -> ScoreResult:
    return ScoreResult(
        overall_score=1.0,
        field_scores=field_scores or [],
        scorer_name="stub",
        scorer_version="0.0.1",
        timestamp_iso=_ISO_UTC,
    )


def _rule_result(
    name: str = "required_fields",
    *,
    passed: bool = True,
    message: str | None = None,
) -> RuleResult:
    return RuleResult(
        rule_name=name,
        passed=passed,
        details={},
        violation_message=message,
    )


def _make_event(
    *,
    source_summary: dict[str, str] | None = None,
    target_summary: dict[str, str] | None = None,
    field_scores: list[FieldScore] | None = None,
    rule_results: list[RuleResult] | None = None,
    triggered_at: str = _ISO_UTC,
) -> ViolationEvent:
    return ViolationEvent(
        contract_name="test_contract",
        contract_version="0.1",
        mode="warn",
        passed=True,
        score_result=_score_result(field_scores),
        rule_results=rule_results or [_rule_result()],
        triggered_at_iso=triggered_at,
        source_summary=source_summary if source_summary is not None else {"hypothesis": "src"},
        target_summary=target_summary if target_summary is not None else {"hypothesis": "tgt"},
    )


# ---------------------------------------------------------------------------
# Construction and field shape
# ---------------------------------------------------------------------------


def test_construct_with_all_required_fields() -> None:
    event = _make_event()
    assert event.contract_name == "test_contract"
    assert event.contract_version == "0.1"
    assert event.mode == "warn"
    assert event.passed is True
    assert event.schema_version == "0.1"


def test_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        ViolationEvent(  # type: ignore[call-arg]
            contract_name="x",
            contract_version="0.1",
            mode="warn",
            passed=True,
            score_result=_score_result(),
            rule_results=[],
            triggered_at_iso=_ISO_UTC,
            source_summary={},
            target_summary={},
            unexpected="boom",
        )


def test_event_id_is_unique_per_construction() -> None:
    e1 = _make_event()
    e2 = _make_event()
    assert e1.event_id != e2.event_id
    # UUID4 string form is 36 chars.
    assert len(e1.event_id) == 36


def test_event_id_round_trip_when_supplied() -> None:
    event = ViolationEvent(
        contract_name="x",
        contract_version="0.1",
        mode="warn",
        passed=True,
        score_result=_score_result(),
        rule_results=[],
        triggered_at_iso=_ISO_UTC,
        source_summary={},
        target_summary={},
        event_id="00000000-0000-4000-8000-000000000001",
    )
    assert event.event_id == "00000000-0000-4000-8000-000000000001"


# ---------------------------------------------------------------------------
# triggered_at_iso validator -- parity with ScoreResult.timestamp_iso
# ---------------------------------------------------------------------------


def test_triggered_at_accepts_explicit_utc_offset() -> None:
    event = _make_event(triggered_at=_ISO_UTC)
    assert event.triggered_at_iso == _ISO_UTC


def test_triggered_at_normalises_z_suffix() -> None:
    # ``Z`` suffix is accepted (normalisation happens in the validator
    # for parsing; the round-tripped string preserves the original).
    event = _make_event(triggered_at="2026-05-10T22:51:00Z")
    assert event.triggered_at_iso == "2026-05-10T22:51:00Z"


def test_triggered_at_rejects_naive() -> None:
    with pytest.raises(ValidationError, match="UTC-offset ISO 8601"):
        _make_event(triggered_at="2026-05-10T22:51:00")


def test_triggered_at_rejects_non_utc_offset() -> None:
    with pytest.raises(ValidationError, match="UTC-offset ISO 8601"):
        _make_event(triggered_at="2026-05-10T22:51:00+01:00")


def test_triggered_at_rejects_garbage() -> None:
    with pytest.raises(ValidationError, match="UTC-offset ISO 8601"):
        _make_event(triggered_at="not a timestamp")


# ---------------------------------------------------------------------------
# to_compact_dict shape and JSON serialisation
# ---------------------------------------------------------------------------


def test_compact_dict_values_are_leaf_scalars() -> None:
    event = _make_event(
        field_scores=[
            FieldScore(field_name="hypothesis", score=0.9, method="embedding_cosine", passed=True),
        ],
        rule_results=[_rule_result(message=None)],
    )
    d = event.to_compact_dict()
    for key, value in d.items():
        assert isinstance(value, str | int | float | bool), (
            f"compact dict value for {key!r} is {type(value).__name__}, expected str|int|float|bool"
        )


def test_compact_dict_json_serialises_round_trip() -> None:
    event = _make_event(
        field_scores=[
            FieldScore(field_name="hypothesis", score=0.9, method="embedding_cosine", passed=True),
        ]
    )
    d = event.to_compact_dict()
    payload = json.dumps(d, ensure_ascii=False, separators=(",", ":"))
    parsed = json.loads(payload)
    assert parsed["precept.contract_name"] == "test_contract"


def test_compact_dict_omits_violation_message_when_none() -> None:
    event = _make_event(rule_results=[_rule_result(passed=True, message=None)])
    d = event.to_compact_dict()
    assert "precept.rule.required_fields.passed" in d
    assert "precept.rule.required_fields.violation_message" not in d


def test_compact_dict_includes_violation_message_when_set() -> None:
    event = _make_event(
        rule_results=[
            _rule_result(passed=False, message="Required field 'x' missing in target payload"),
        ],
    )
    d = event.to_compact_dict()
    assert (
        d["precept.rule.required_fields.violation_message"]
        == "Required field 'x' missing in target payload"
    )


def test_compact_dict_normal_event_has_no_truncation_flag() -> None:
    event = _make_event()
    d = event.to_compact_dict()
    assert "precept.payload_truncated" not in d


# ---------------------------------------------------------------------------
# 4 KiB ceiling and truncation order
# ---------------------------------------------------------------------------


def _byte_size(d: dict[str, str | int | float | bool]) -> int:
    return len(json.dumps(d, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def test_compact_dict_truncates_when_summaries_inflated() -> None:
    big = "x" * 5000
    event = _make_event(
        source_summary={"a": big},
        target_summary={"b": big},
    )
    d = event.to_compact_dict()
    assert _byte_size(d) <= 4096
    assert d.get("precept.payload_truncated") is True


def test_compact_dict_drops_target_before_source() -> None:
    # Big target value forces truncation; small source survives.
    big_target = "x" * 4500
    small_source = "y" * 100
    event = _make_event(
        source_summary={"a": small_source},
        target_summary={"b": big_target},
    )
    d = event.to_compact_dict()
    assert _byte_size(d) <= 4096
    assert "precept.target.b" not in d
    assert d["precept.source.a"] == small_source
    assert d.get("precept.payload_truncated") is True


def test_compact_dict_drops_source_after_target_exhausted() -> None:
    # Both sides are large; both must drop to fit.
    huge = "x" * 6000
    event = _make_event(
        source_summary={"a": huge},
        target_summary={"b": huge},
    )
    d = event.to_compact_dict()
    assert _byte_size(d) <= 4096
    assert "precept.target.b" not in d
    assert "precept.source.a" not in d
    assert d.get("precept.payload_truncated") is True


def test_compact_dict_irreducible_overflow_terminates_and_flags() -> None:
    """Irreducible-overflow path: empty summaries but enough rule_results
    to push the base dict past 4 KiB on its own.

    The truncation loop has nothing to drop, hits ``break``, and must:
    (1) terminate (no infinite loop), and
    (2) set ``precept.payload_truncated`` so backends can flag the
    event as over-budget even though Precept could not shrink it.
    """
    event = ViolationEvent(
        contract_name="x",
        contract_version="0.1",
        mode="warn",
        passed=False,
        score_result=_score_result(),
        rule_results=[
            RuleResult(
                rule_name=f"r{i:03d}",
                passed=False,
                violation_message="x" * 80,
            )
            for i in range(50)
        ],
        triggered_at_iso=_ISO_UTC,
        source_summary={},
        target_summary={},
    )
    d = event.to_compact_dict()
    assert d.get("precept.payload_truncated") is True
    # Guard against an unintended drop path: there were no source/target
    # keys to drop, so neither prefix should appear in the result.
    assert not any(k.startswith("precept.target.") for k in d)
    assert not any(k.startswith("precept.source.") for k in d)


# ---------------------------------------------------------------------------
# Schema-drift canary
# ---------------------------------------------------------------------------


_EXPECTED_VIOLATION_EVENT_FIELDS = {
    "contract_name",
    "contract_version",
    "mode",
    "passed",
    "score_result",
    "rule_results",
    "triggered_at_iso",
    "event_id",
    "source_summary",
    "target_summary",
    "schema_version",
}


def test_violation_event_field_set_matches_expected() -> None:
    """Schema-drift canary.

    Adding, removing, or renaming a ``ViolationEvent`` field MUST be
    paired with an update to ``to_compact_dict``'s key layout (and to
    this expected set). Failing this test loudly is the contract.
    """
    assert set(ViolationEvent.model_fields) == _EXPECTED_VIOLATION_EVENT_FIELDS


def test_compact_dict_covers_all_top_level_prefixes() -> None:
    """Every top-level model field maps to at least one ``precept.*`` key.

    Co-located with the field-set canary so a model rename without a
    flattener update fails this assertion (rather than silently producing
    a compact dict missing data).
    """
    event = _make_event(
        field_scores=[
            FieldScore(field_name="hypothesis", score=0.9, method="embedding_cosine", passed=True),
        ],
    )
    d = event.to_compact_dict()
    keys = set(d.keys())
    expected = {
        "precept.contract_name",
        "precept.contract_version",
        "precept.mode",
        "precept.passed",
        "precept.event_id",
        "precept.schema_version",
        "precept.triggered_at_iso",
        "precept.score.overall",
        "precept.score.scorer_name",
        "precept.score.scorer_version",
        "precept.score.timestamp_iso",
        "precept.score.field.hypothesis.score",
        "precept.score.field.hypothesis.method",
        "precept.score.field.hypothesis.passed",
        "precept.rule.required_fields.passed",
        "precept.source.hypothesis",
        "precept.target.hypothesis",
    }
    missing = expected - keys
    assert not missing, f"compact dict missing expected keys: {sorted(missing)}"
