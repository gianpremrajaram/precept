# SPDX-License-Identifier: MIT
"""Tests for ``precept.exporters.base`` (PRC-013).

Covers the :class:`Exporter` ABC's ``__init_subclass__`` enforcement
(mirror of :class:`Scorer`'s pattern), the :class:`NoOpExporter`
default sink, and :class:`MultiExporter`'s per-exporter failure
isolation.
"""

from __future__ import annotations

import logging
from abc import abstractmethod
from typing import ClassVar

import pytest

from precept.evaluator.rules import RuleResult
from precept.exporters.base import Exporter, MultiExporter, NoOpExporter
from precept.scoring.base import ScoreResult
from precept.types import ViolationEvent

_ISO_UTC = "2026-05-10T22:51:00+00:00"


def _make_event() -> ViolationEvent:
    return ViolationEvent(
        contract_name="x",
        contract_version="0.1",
        mode="warn",
        passed=True,
        score_result=ScoreResult(
            overall_score=1.0,
            field_scores=[],
            scorer_name="stub",
            scorer_version="0.0.1",
            timestamp_iso=_ISO_UTC,
        ),
        rule_results=[RuleResult(rule_name="required_fields", passed=True)],
        triggered_at_iso=_ISO_UTC,
        source_summary={},
        target_summary={},
    )


# ---------------------------------------------------------------------------
# ABC instantiation guard
# ---------------------------------------------------------------------------


def test_exporter_abc_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        Exporter()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# __init_subclass__ enforcement
# ---------------------------------------------------------------------------


def test_subclass_missing_name_raises_at_class_definition() -> None:
    with pytest.raises(TypeError, match="non-empty class-level 'name'"):

        class _Bad(Exporter):
            def export(self, event: ViolationEvent) -> None:
                return None


def test_subclass_with_empty_name_raises() -> None:
    with pytest.raises(TypeError, match="non-empty class-level 'name'"):

        class _Bad(Exporter):
            name: ClassVar[str] = ""

            def export(self, event: ViolationEvent) -> None:
                return None


def test_subclass_with_non_string_name_raises() -> None:
    with pytest.raises(TypeError, match="non-empty class-level 'name'"):

        class _Bad(Exporter):
            name = 123  # type: ignore[assignment]

            def export(self, event: ViolationEvent) -> None:
                return None


def test_intermediate_abstract_subclass_exempt_from_name_check() -> None:
    # Intermediate subclass that does NOT implement ``export`` is still
    # abstract. ``__init_subclass__`` skips the name check for
    # intermediates (mirrors Scorer pattern); class definition succeeds.

    class _Intermediate(Exporter):
        @abstractmethod
        def export(self, event: ViolationEvent) -> None: ...

    # Constructing the intermediate fails (still abstract), but defining
    # it must not raise.
    with pytest.raises(TypeError):
        _Intermediate()  # type: ignore[abstract]


def test_concrete_subclass_with_valid_name_succeeds() -> None:
    class _OK(Exporter):
        name: ClassVar[str] = "ok"

        def export(self, event: ViolationEvent) -> None:
            return None

    instance = _OK()
    assert instance.name == "ok"


# ---------------------------------------------------------------------------
# NoOpExporter
# ---------------------------------------------------------------------------


def test_noop_exporter_name_is_noop() -> None:
    assert NoOpExporter.name == "noop"


def test_noop_exporter_export_returns_none() -> None:
    NoOpExporter().export(_make_event())


# ---------------------------------------------------------------------------
# MultiExporter
# ---------------------------------------------------------------------------


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


def test_multi_exporter_name_is_multi() -> None:
    assert MultiExporter.name == "multi"


def test_multi_exporter_calls_all_children_in_order() -> None:
    a, b = _Recording(), _Recording()
    multi = MultiExporter([a, b])
    event = _make_event()
    multi.export(event)
    assert a.received == [event]
    assert b.received == [event]


def test_multi_exporter_isolates_failures(caplog: pytest.LogCaptureFixture) -> None:
    failing = _Failing()
    working = _Recording()
    multi = MultiExporter([failing, working])
    event = _make_event()
    with caplog.at_level(logging.WARNING, logger="precept.exporters.base"):
        multi.export(event)
    assert working.received == [event], "working exporter must still receive the event"
    # Failure was logged, not raised.
    joined = " ".join(rec.getMessage() for rec in caplog.records)
    assert "failing" in joined or "simulated transport failure" in joined


def test_multi_exporter_empty_list_is_silent_success() -> None:
    multi = MultiExporter([])
    multi.export(_make_event())  # no error, no children to call


def test_multi_exporter_continues_after_first_child_fails() -> None:
    # Order: failing -> working1 -> failing -> working2.
    working1 = _Recording()
    working2 = _Recording()
    multi = MultiExporter([_Failing(), working1, _Failing(), working2])
    event = _make_event()
    multi.export(event)
    assert working1.received == [event]
    assert working2.received == [event]
