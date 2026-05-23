# SPDX-License-Identifier: MIT
"""End-to-end evaluator integration against the committed demo fixtures (PRC-017).

Loads the real ``EmbeddingProxy``, loads the YAML contracts from
``examples/contracts/``, and runs ``Evaluator.evaluate`` on every hop in
the clean and degraded fixtures. The clean trace must produce zero
violations across the pipeline; the degraded trace must produce exactly
two rule violations (``preserved_entities`` and ``forbidden_drops``) at
the summariser->writer hop, with no score-gate failures.

Contracts and fixtures are co-designed: ``preserved_entities`` lists
domain strings (e.g. ``"MCS Quarterly Statistics"``) that appear
verbatim in the source payload values; the degraded target drops the
field carrying those substrings, so ``preserved_entities_rule`` fires
naturally without any fixture-side workaround.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from precept.contract.schema import HandoffContract
from precept.contract.yaml_loader import load_contract
from precept.evaluator.engine import Evaluator
from precept.evaluator.rules import RuleResult
from precept.exporters.base import NoOpExporter
from precept.scoring.base import HandoffPayload
from precept.scoring.embedding_proxy import EmbeddingProxy
from precept.types import ViolationEvent

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CONTRACTS_DIR = _REPO_ROOT / "examples" / "contracts"


@pytest.fixture(scope="module")
def evaluator() -> Evaluator:
    return Evaluator(EmbeddingProxy(), NoOpExporter())


@pytest.fixture(scope="module")
def contracts() -> dict[str, HandoffContract]:
    return {
        "researcher_to_summariser": load_contract(_CONTRACTS_DIR / "researcher_to_summariser.yaml"),
        "summariser_to_writer": load_contract(_CONTRACTS_DIR / "summariser_to_writer.yaml"),
    }


def _evaluate_trace(
    evaluator: Evaluator,
    contracts: dict[str, HandoffContract],
    trace: dict[str, Any],
) -> list[ViolationEvent]:
    events: list[ViolationEvent] = []
    for hop in trace["hops"]:
        contract = contracts[hop["handoff_metadata"]["contract_name"]]
        source = HandoffPayload(fields=hop["source_payload"])
        target = HandoffPayload(fields=hop["target_payload"])
        events.append(evaluator.evaluate(source, target, contract))
    return events


def _rule(events_first_hop: list[RuleResult], name: str) -> RuleResult:
    for r in events_first_hop:
        if r.rule_name == name:
            return r
    raise AssertionError(f"rule {name!r} not present in evaluator output")


def test_clean_trace_produces_no_violations(
    evaluator: Evaluator,
    contracts: dict[str, HandoffContract],
    clean_trace: dict[str, Any],
) -> None:
    events = _evaluate_trace(evaluator, contracts, clean_trace)

    assert len(events) == len(clean_trace["hops"])
    for hop, event in zip(clean_trace["hops"], events, strict=True):
        meta = hop["handoff_metadata"]
        rule_summary = [(r.rule_name, r.passed) for r in event.rule_results]
        score_summary = [
            (fs.field_name, fs.score, fs.passed) for fs in event.score_result.field_scores
        ]
        assert event.passed is True, (
            f"clean trace produced a violation at "
            f"{meta['source_agent']}->{meta['target_agent']}: "
            f"rules={rule_summary}, field_scores={score_summary}"
        )
        assert all(r.passed for r in event.rule_results)
        assert all(fs.passed for fs in event.score_result.field_scores)


def test_degraded_trace_fails_only_at_summariser_to_writer(
    evaluator: Evaluator,
    contracts: dict[str, HandoffContract],
    degraded_trace: dict[str, Any],
) -> None:
    events = _evaluate_trace(evaluator, contracts, degraded_trace)
    assert len(events) == 2

    researcher_hop, summariser_hop = events
    assert researcher_hop.passed is True, (
        "researcher->summariser hop should be clean in the degraded trace"
    )

    assert summariser_hop.passed is False
    assert summariser_hop.contract_name == "summariser_to_writer"

    failing_rules = [r for r in summariser_hop.rule_results if not r.passed]
    failing_rule_names = sorted(r.rule_name for r in failing_rules)
    assert failing_rule_names == ["forbidden_drops", "preserved_entities"], (
        "degraded summariser->writer hop must fail exactly preserved_entities and forbidden_drops; "
        f"got {failing_rule_names!r}"
    )

    preserved = _rule(summariser_hop.rule_results, "preserved_entities")
    assert preserved.details == {
        "entities": ["MCS Quarterly Statistics"],
        "missing": ["MCS Quarterly Statistics"],
    }

    forbidden = _rule(summariser_hop.rule_results, "forbidden_drops")
    assert forbidden.details == {
        "forbidden": ["uncertainty_bounds"],
        "dropped": ["uncertainty_bounds"],
    }

    # Score gate must NOT contribute to the failure: rules drive the demo violation.
    assert all(fs.passed for fs in summariser_hop.score_result.field_scores), (
        "degraded summariser->writer score-gate failures would muddy the demo signal; "
        "score_result must show passed=True per field for the rule-only violation story to hold."
    )
