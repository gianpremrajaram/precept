# SPDX-License-Identifier: Apache-2.0
"""Unit tests for ``precept.integrations.langgraph.eval_hook`` (PRC-014).

Covers the six AC cases (valid contract returns event; block+fail
raises; warn+fail emits without raising; missing contract fails open;
``raise_on_block=False`` never raises; async-context dispatch does not
starve the loop) plus the lazy default-evaluator cache and the
``default_registry`` fallback.

This module imports no ``langgraph`` symbol -- mirroring the module under
test -- so it runs in environments where ``langgraph`` is absent.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import ClassVar

import pytest

from precept.contract.registry import ContractRegistry
from precept.contract.schema import ContractFields, HandoffContract
from precept.errors import HandoffBlockedError
from precept.evaluator.engine import Evaluator
from precept.exporters.base import Exporter
from precept.integrations.langgraph import eval_hook
from precept.integrations.langgraph.eval_hook import evaluate_handoff
from precept.scoring.base import FieldScore, HandoffPayload, Scorer, ScoreResult
from precept.types import ViolationEvent


class StubScorer(Scorer):
    """Deterministic scorer; per-field score configurable, default 1.0.

    Threshold mirrors :class:`EmbeddingProxy`: ``contract.fields.
    min_fidelity`` or ``0.5``. Scores ``contract.fields.required_fields``.
    """

    name: ClassVar[str] = "stub"
    version: ClassVar[str] = "0.0.1"

    def __init__(self, *, per_field: dict[str, float] | None = None, default: float = 1.0) -> None:
        self._per_field = per_field or {}
        self._default = default

    def score(
        self, source: HandoffPayload, target: HandoffPayload, contract: HandoffContract
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


class _SlowScorer(Scorer):
    """Sleeps to simulate the ~500 ms blocking inference of the v0 scorer."""

    name: ClassVar[str] = "slow"
    version: ClassVar[str] = "0.0.1"

    def score(
        self, source: HandoffPayload, target: HandoffPayload, contract: HandoffContract
    ) -> ScoreResult:
        time.sleep(0.12)
        return ScoreResult(
            overall_score=1.0,
            field_scores=[],
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


def _contract(
    name: str, *, mode: str = "block", required: list[str] | None = None
) -> HandoffContract:
    return HandoffContract(
        name=name,
        mode=mode,
        fields=ContractFields(required_fields=required if required is not None else ["body"]),
    )


def _registry(contract: HandoffContract) -> ContractRegistry:
    reg = ContractRegistry()
    reg.register(contract)
    return reg


# --- AC: valid contract evaluates and returns the event -------------------


def test_valid_contract_evaluates_and_returns_event() -> None:
    rec = _Recording()
    ev = Evaluator(StubScorer(), rec)
    contract = _contract("ehk_pass", mode="warn")

    event = evaluate_handoff(
        {"body": "x"}, {"body": "y"}, "ehk_pass", registry=_registry(contract), evaluator=ev
    )

    assert isinstance(event, ViolationEvent)
    assert event.passed is True
    assert event.contract_name == "ehk_pass"
    assert rec.received == [event]


# --- AC: block mode + failing contract raises -----------------------------


def test_block_mode_failing_contract_raises() -> None:
    rec = _Recording()
    ev = Evaluator(StubScorer(per_field={"body": 0.4}), rec)
    contract = _contract("ehk_block", mode="block")

    with pytest.raises(HandoffBlockedError) as excinfo:
        evaluate_handoff(
            {"body": "x"}, {"body": "y"}, "ehk_block", registry=_registry(contract), evaluator=ev
        )

    err = excinfo.value
    assert err.violation_event.passed is False
    # PRC-015 wiring: impact summary populated before raise.
    assert err.impact_summary != ""
    assert "ehk_block" in err.impact_summary
    # Evaluator still exported the event before the hook raised.
    assert len(rec.received) == 1
    assert rec.received[0].passed is False


# --- AC: warn mode + failing contract emits but does not raise ------------


def test_warn_mode_failing_contract_emits_without_raising() -> None:
    rec = _Recording()
    ev = Evaluator(StubScorer(per_field={"body": 0.4}), rec)
    contract = _contract("ehk_warn", mode="warn")

    event = evaluate_handoff(
        {"body": "x"}, {"body": "y"}, "ehk_warn", registry=_registry(contract), evaluator=ev
    )

    assert event.passed is False
    assert rec.received == [event]


# --- AC: missing contract fails open --------------------------------------


def test_missing_contract_fails_open(caplog: pytest.LogCaptureFixture) -> None:
    rec = _Recording()
    ev = Evaluator(StubScorer(), rec)
    caplog.set_level(logging.WARNING, logger="precept.integrations.langgraph.eval_hook")

    event = evaluate_handoff(
        {"body": "x"}, {"body": "y"}, "no_such_contract", registry=ContractRegistry(), evaluator=ev
    )

    assert event.passed is True
    assert event.contract_name == "no_such_contract"
    assert event.contract_version == "unknown"
    assert event.mode == "warn"
    assert event.score_result.scorer_name == "synthetic"
    assert event.rule_results == []
    # Synthetic event is returned but never exported.
    assert rec.received == []
    assert any(r.levelno == logging.WARNING and "failing open" in r.message for r in caplog.records)


# --- AC: raise_on_block=False never raises --------------------------------


def test_raise_on_block_false_never_raises() -> None:
    ev = Evaluator(StubScorer(per_field={"body": 0.4}))
    contract = _contract("ehk_noraise", mode="block")

    event = evaluate_handoff(
        {"body": "x"},
        {"body": "y"},
        "ehk_noraise",
        registry=_registry(contract),
        evaluator=ev,
        raise_on_block=False,
    )

    assert event.passed is False  # would have raised if raise_on_block defaulted


# --- AC: async-context dispatch -------------------------------------------


def test_evaluate_handoff_in_running_loop_returns_event() -> None:
    """Called bare from inside a running loop, the hook offloads
    ``evaluate`` to a worker thread and still returns a valid event
    (the in-loop branch must not deadlock)."""
    ev = Evaluator(StubScorer())
    reg = _registry(_contract("ehk_loop", mode="warn"))

    async def run() -> ViolationEvent:
        return evaluate_handoff(
            {"body": "x"}, {"body": "y"}, "ehk_loop", registry=reg, evaluator=ev
        )

    event = asyncio.run(run())
    assert isinstance(event, ViolationEvent)
    assert event.passed is True


def test_evaluate_handoff_via_to_thread_does_not_block_loop() -> None:
    """The documented non-blocking idiom ``await asyncio.to_thread(
    evaluate_handoff, ...)`` keeps concurrent loop tasks progressing
    while the slow scorer runs (PRC-011 precedent; AC measure-ticks)."""
    ev = Evaluator(_SlowScorer())
    reg = _registry(_contract("ehk_async", mode="warn"))

    async def run() -> tuple[ViolationEvent, int]:
        ticks = 0

        async def tick() -> None:
            nonlocal ticks
            for _ in range(20):
                await asyncio.sleep(0.005)
                ticks += 1

        tick_task = asyncio.create_task(tick())
        event = await asyncio.to_thread(
            evaluate_handoff,
            {"body": "x"},
            {"body": "y"},
            "ehk_async",
            registry=reg,
            evaluator=ev,
        )
        await tick_task
        return event, ticks

    event, ticks = asyncio.run(run())
    assert event.passed is True
    assert ticks >= 5


# --- Lazy default evaluator + default_registry fallback -------------------


def test_default_evaluator_built_once_and_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    """The module default is constructed lazily and exactly once -- never
    at import (see module docstring; resolves GPT review Issue 2)."""
    constructed = 0

    class _FakeProxy:
        def __init__(self) -> None:
            nonlocal constructed
            constructed += 1

    monkeypatch.setattr(eval_hook, "_DEFAULT_EVALUATOR", None)
    monkeypatch.setattr("precept.scoring.embedding_proxy.EmbeddingProxy", _FakeProxy, raising=True)

    first = eval_hook._default_evaluator()
    second = eval_hook._default_evaluator()

    assert first is second
    assert constructed == 1


def test_registry_defaults_to_default_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    rec = _Recording()
    ev = Evaluator(StubScorer(), rec)
    fresh = _registry(_contract("ehk_defaultreg", mode="warn"))
    monkeypatch.setattr(eval_hook, "default_registry", fresh)

    event = evaluate_handoff({"body": "x"}, {"body": "y"}, "ehk_defaultreg", evaluator=ev)

    assert event.contract_name == "ehk_defaultreg"
    assert rec.received == [event]


# --- Module surface -------------------------------------------------------


def test_module_all_is_complete_and_sorted() -> None:
    assert eval_hook.__all__ == sorted(eval_hook.__all__)
    for symbol in eval_hook.__all__:
        assert hasattr(eval_hook, symbol)
