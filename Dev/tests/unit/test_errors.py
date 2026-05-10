# SPDX-License-Identifier: MIT
"""Tests for ``precept.errors`` (PRC-006 + PRC-013).

Covers ``HandoffBlockedError`` introduced in PRC-013 (carrier
behaviour, default empty ``impact_summary``, post-construction
mutation pattern, constructor kwarg) plus a subprocess leaf-import
regression that asserts the PRC-014 ⇄ PRC-015 cycle remains broken.

``ContractValidationError`` continues to be tested in
``tests/unit/contract/test_schema.py``; the smoke regression here is
just that the symbol still imports from this module.
"""

from __future__ import annotations

import subprocess
import sys

from precept.errors import ContractValidationError, HandoffBlockedError
from precept.evaluator.rules import RuleResult
from precept.scoring.base import ScoreResult
from precept.types import ViolationEvent

_ISO_UTC = "2026-05-10T22:51:00+00:00"


def _make_event() -> ViolationEvent:
    return ViolationEvent(
        contract_name="researcher_to_summariser",
        contract_version="0.1",
        mode="block",
        passed=False,
        score_result=ScoreResult(
            overall_score=0.4,
            field_scores=[],
            scorer_name="stub",
            scorer_version="0.0.1",
            timestamp_iso=_ISO_UTC,
        ),
        rule_results=[RuleResult(rule_name="required_fields", passed=True)],
        triggered_at_iso=_ISO_UTC,
        source_summary={"hypothesis": "src"},
        target_summary={"hypothesis": "tgt"},
    )


def test_contract_validation_error_still_importable() -> None:
    # Regression: PRC-006's exception class still lives at this path.
    assert issubclass(ContractValidationError, Exception)


def test_handoff_blocked_error_carries_event() -> None:
    event = _make_event()
    err = HandoffBlockedError(event)
    assert err.violation_event is event


def test_handoff_blocked_error_default_impact_summary_is_empty() -> None:
    err = HandoffBlockedError(_make_event())
    assert err.impact_summary == ""


def test_handoff_blocked_error_constructor_kwarg() -> None:
    # Pre-rendered summary path: bypasses the post-construction
    # populator entirely.
    err = HandoffBlockedError(_make_event(), impact_summary="prefilled")
    assert err.impact_summary == "prefilled"


def test_handoff_blocked_error_post_construction_mutation() -> None:
    # Documented contract: PRC-015's populator writes onto an existing
    # instance immediately before re-raise. The field is mutable by
    # design.
    event = _make_event()
    err = HandoffBlockedError(event)
    err.impact_summary = "PFOA citations were dropped at the boundary"
    assert err.impact_summary == "PFOA citations were dropped at the boundary"
    # Event itself is unchanged by the impact-summary mutation.
    assert err.violation_event is event


def test_handoff_blocked_error_message_names_contract() -> None:
    err = HandoffBlockedError(_make_event())
    # The exception args carry a one-liner; richer detail lives on the
    # attached event. Useful for default ``str(err)`` rendering.
    assert "researcher_to_summariser" in str(err)


def test_handoff_blocked_error_leaf_import_no_evaluator_or_proxy() -> None:
    """Subprocess regression: importing ``HandoffBlockedError`` must not
    transitively load the evaluator engine or the embedding-proxy
    scorer.

    PRC-014 imports ``HandoffBlockedError`` from
    :mod:`precept.errors`; the cycle-break invariant requires no edge
    from :mod:`precept.errors` back into the integration layer or the
    scorer concrete. Asserting the absence of those modules in
    ``sys.modules`` after the import confirms the invariant.
    """
    code = (
        "import sys\n"
        "from precept.errors import HandoffBlockedError\n"
        "assert HandoffBlockedError is not None\n"
        "assert 'precept.evaluator.engine' not in sys.modules, sorted(sys.modules)\n"
        "assert 'precept.scoring.embedding_proxy' not in sys.modules, sorted(sys.modules)\n"
        "print('ok')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"subprocess failed: stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert result.stdout.strip() == "ok"
