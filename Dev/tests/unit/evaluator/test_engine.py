# SPDX-License-Identifier: MIT
"""Tests for ``precept.evaluator.engine.Evaluator`` (PRC-013).

Uses an inline ``StubScorer`` so unit tests run without the
sentence-transformer model download. The integration tier exercises
the real :class:`EmbeddingProxy` end-to-end.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import ClassVar

import pytest

from precept.contract.schema import ContractFields, HandoffContract
from precept.evaluator.engine import Evaluator
from precept.exporters.base import Exporter, MultiExporter, NoOpExporter
from precept.scoring.base import FieldScore, HandoffPayload, Scorer, ScoreResult
from precept.types import ViolationEvent

# ---------------------------------------------------------------------------
# Stub scorer / exporters
# ---------------------------------------------------------------------------


class StubScorer(Scorer):
    """Deterministic scorer; per-field score configurable, default 1.0.

    Threshold is read from ``contract.fields.min_fidelity`` (falling back
    to ``0.5``), mirroring :class:`EmbeddingProxy`'s fallback.
    """

    name: ClassVar[str] = "stub"
    version: ClassVar[str] = "0.0.1"

    def __init__(
        self,
        *,
        per_field: dict[str, float] | None = None,
        default: float = 1.0,
    ) -> None:
        self._per_field = per_field or {}
        self._default = default

    def score(
        self,
        source: HandoffPayload,
        target: HandoffPayload,
        contract: HandoffContract,
    ) -> ScoreResult:
        threshold = (
            contract.fields.min_fidelity if contract.fields.min_fidelity is not None else 0.5
        )
        field_scores = [
            FieldScore(
                field_name=name,
                score=self._per_field.get(name, self._default),
                method="stub",
                passed=self._per_field.get(name, self._default) >= threshold,
            )
            for name in contract.fields.required_fields
        ]
        overall = sum(fs.score for fs in field_scores) / len(field_scores) if field_scores else 1.0
        return ScoreResult(
            overall_score=overall,
            field_scores=field_scores,
            scorer_name=self.name,
            scorer_version=self.version,
            timestamp_iso=datetime.now(timezone.utc).isoformat(),
        )


class _Recording(Exporter):
    name: ClassVar[str] = "recording"

    def __init__(self) -> None:
        self.received: list[ViolationEvent] = []

    def export(self, event: ViolationEvent) -> None:
        self.received.append(event)


class _Failing(Exporter):
    name: ClassVar[str] = "failing"

    def export(self, event: ViolationEvent) -> None:
        raise RuntimeError("simulated transport failure")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _contract(
    *,
    required: list[str] | None = None,
    preserved: list[str] | None = None,
    forbidden: list[str] | None = None,
    min_fidelity: float | None = 0.75,
    mode: str = "block",
) -> HandoffContract:
    return HandoffContract(
        name="test_contract",
        mode=mode,
        fields=ContractFields(
            required_fields=required or [],
            preserved_entities=preserved or [],
            forbidden_drops=forbidden or [],
            min_fidelity=min_fidelity,
        ),
    )


def _source_target(
    source_fields: dict[str, object] | None = None,
    target_fields: dict[str, object] | None = None,
) -> tuple[HandoffPayload, HandoffPayload]:
    return (
        HandoffPayload(fields=source_fields or {}),
        HandoffPayload(fields=target_fields or {}),
    )


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_evaluator_default_exporter_is_noop() -> None:
    ev = Evaluator(StubScorer())
    assert isinstance(ev.exporter, NoOpExporter)


def test_evaluator_accepts_explicit_exporter() -> None:
    rec = _Recording()
    ev = Evaluator(StubScorer(), rec)
    assert ev.exporter is rec


def test_evaluator_scorer_accessor() -> None:
    scorer = StubScorer()
    ev = Evaluator(scorer)
    assert ev.scorer is scorer


# ---------------------------------------------------------------------------
# evaluate(): pass / fail aggregation
# ---------------------------------------------------------------------------


def test_clean_handoff_passes() -> None:
    contract = _contract(required=["hypothesis", "citations"])
    source, target = _source_target(
        {"hypothesis": "h", "citations": "c"},
        {"hypothesis": "h", "citations": "c"},
    )
    ev = Evaluator(StubScorer(default=1.0))
    event = ev.evaluate(source, target, contract)
    assert event.passed is True
    assert all(r.passed for r in event.rule_results)
    assert all(fs.passed for fs in event.score_result.field_scores)


def test_required_field_missing_fails() -> None:
    contract = _contract(required=["hypothesis", "citations"])
    source, target = _source_target(
        {"hypothesis": "h", "citations": "c"},
        {"hypothesis": "h"},  # citations dropped
    )
    ev = Evaluator(StubScorer())
    event = ev.evaluate(source, target, contract)
    assert event.passed is False
    by_rule = {r.rule_name: r for r in event.rule_results}
    assert by_rule["required_fields"].passed is False
    assert "citations" in (by_rule["required_fields"].violation_message or "")


def test_preserved_entity_dropped_fails() -> None:
    # Contract that uses preserved_entities. min_fidelity required by IR.
    contract = _contract(
        required=["body"],
        preserved=["PFOA"],
        min_fidelity=0.5,
    )
    source, target = _source_target(
        {"body": "Sustained PFOA exposure correlates with renal effects."},
        {"body": "Sustained chemical exposure correlates with renal effects."},
    )
    ev = Evaluator(StubScorer())
    event = ev.evaluate(source, target, contract)
    assert event.passed is False
    by_rule = {r.rule_name: r for r in event.rule_results}
    assert by_rule["preserved_entities"].passed is False


def test_forbidden_drop_fails() -> None:
    contract = _contract(required=["body"], forbidden=["uncertainty_bounds"])
    source, target = _source_target(
        {"body": "claims", "uncertainty_bounds": "+/- 0.05"},
        {"body": "claims"},  # uncertainty_bounds dropped
    )
    ev = Evaluator(StubScorer())
    event = ev.evaluate(source, target, contract)
    assert event.passed is False
    by_rule = {r.rule_name: r for r in event.rule_results}
    assert by_rule["forbidden_drops"].passed is False


def test_field_score_below_threshold_fails_overall() -> None:
    # Rules all pass, but a single failing FieldScore must flip ``passed``.
    contract = _contract(required=["body"], min_fidelity=0.75)
    source, target = _source_target({"body": "h"}, {"body": "h"})
    ev = Evaluator(StubScorer(per_field={"body": 0.4}))
    event = ev.evaluate(source, target, contract)
    assert all(r.passed for r in event.rule_results)
    assert event.score_result.field_scores[0].passed is False
    assert event.passed is False


def test_event_id_distinct_across_calls() -> None:
    contract = _contract(required=["body"])
    source, target = _source_target({"body": "h"}, {"body": "h"})
    ev = Evaluator(StubScorer())
    ids = {ev.evaluate(source, target, contract).event_id for _ in range(100)}
    assert len(ids) == 100


# ---------------------------------------------------------------------------
# Summaries
# ---------------------------------------------------------------------------


def test_summaries_truncate_long_string_values_to_100_chars() -> None:
    long_value = "a" * 300
    contract = _contract(required=["body"])
    source, target = _source_target({"body": long_value}, {"body": long_value})
    ev = Evaluator(StubScorer())
    event = ev.evaluate(source, target, contract)
    assert len(event.source_summary["body"]) == 100
    assert len(event.target_summary["body"]) == 100
    assert event.source_summary["body"] == "a" * 100


def test_summaries_stringify_non_string_values() -> None:
    contract = _contract(required=["count"])
    source, target = _source_target({"count": 42}, {"count": 42})
    ev = Evaluator(StubScorer())
    event = ev.evaluate(source, target, contract)
    assert event.source_summary["count"] == "42"
    assert event.target_summary["count"] == "42"


# ---------------------------------------------------------------------------
# Exporter dispatch and failure isolation
# ---------------------------------------------------------------------------


def test_default_noop_exporter_does_not_raise() -> None:
    contract = _contract(required=["body"])
    source, target = _source_target({"body": "h"}, {"body": "h"})
    ev = Evaluator(StubScorer())
    # Just calling evaluate() exercises the default exporter path.
    event = ev.evaluate(source, target, contract)
    assert event.passed is True


def test_recording_exporter_receives_event() -> None:
    rec = _Recording()
    contract = _contract(required=["body"])
    source, target = _source_target({"body": "h"}, {"body": "h"})
    ev = Evaluator(StubScorer(), rec)
    event = ev.evaluate(source, target, contract)
    assert rec.received == [event]


def test_failing_exporter_does_not_propagate(caplog: pytest.LogCaptureFixture) -> None:
    contract = _contract(required=["body"])
    source, target = _source_target({"body": "h"}, {"body": "h"})
    ev = Evaluator(StubScorer(), _Failing())
    with caplog.at_level(logging.WARNING, logger="precept.evaluator.engine"):
        event = ev.evaluate(source, target, contract)
    assert event.passed is True  # evaluation result preserved
    joined = " ".join(rec.getMessage() for rec in caplog.records)
    assert "failing" in joined or "simulated transport failure" in joined


def test_multi_exporter_with_failing_first_still_delivers_to_working() -> None:
    rec = _Recording()
    multi = MultiExporter([_Failing(), rec])
    contract = _contract(required=["body"])
    source, target = _source_target({"body": "h"}, {"body": "h"})
    ev = Evaluator(StubScorer(), multi)
    event = ev.evaluate(source, target, contract)
    assert rec.received == [event]
