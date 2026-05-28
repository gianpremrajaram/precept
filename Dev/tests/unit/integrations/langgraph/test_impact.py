# SPDX-License-Identifier: Apache-2.0
"""Unit tests for ``precept.integrations.langgraph.impact`` (PRC-015).

Covers the five AC cases (every template renders; in-place mutation
with the attached event left unmodified; unknown combination falls
back; the rendered string carries every token; demo-omission
regression) plus the two robustness branches the populator must handle
because it receives an arbitrary :class:`HandoffBlockedError`: agent
derivation from the ``<source>_to_<target>`` contract-name convention
(with the no-infix fallback) and the pure score-gate block where no
rule failed.
"""

from __future__ import annotations

from precept.errors import HandoffBlockedError
from precept.evaluator.rules import RuleResult
from precept.integrations.langgraph.impact import (
    DEFAULT_IMPACT_FALLBACK,
    IMPACT_TEMPLATES,
    populate_impact_summary,
    render_impact_text,
)
from precept.scoring.base import ScoreResult
from precept.types import ViolationEvent

_ISO_UTC = "2026-05-10T22:51:00+00:00"

# Demo contract+rule combinations PRC-018 ships; the omission regression
# (test_all_demo_combinations_have_entries) asserts every pair below is a
# key in IMPACT_TEMPLATES so a contract rename cannot silently degrade to
# the generic fallback.
_DEMO_COMBINATIONS = [
    ("researcher_to_summariser", "required_fields"),
    ("researcher_to_summariser", "preserved_entities"),
    ("summariser_to_writer", "preserved_entities"),
    ("summariser_to_writer", "forbidden_drops"),
]


def _rule(name: str, *, passed: bool) -> RuleResult:
    return RuleResult(
        rule_name=name,
        passed=passed,
        details={},
        violation_message=None if passed else f"{name} failed",
    )


def _blocked_error(
    *,
    contract_name: str = "researcher_to_summariser",
    rule_results: list[RuleResult] | None = None,
) -> HandoffBlockedError:
    if rule_results is None:
        rule_results = [
            _rule("required_fields", passed=False),
            _rule("preserved_entities", passed=True),
            _rule("forbidden_drops", passed=True),
        ]
    event = ViolationEvent(
        contract_name=contract_name,
        contract_version="0.1",
        mode="block",
        passed=False,
        score_result=ScoreResult(
            overall_score=0.0,
            field_scores=[],
            scorer_name="stub",
            scorer_version="0.0.1",
            timestamp_iso=_ISO_UTC,
        ),
        rule_results=rule_results,
        triggered_at_iso=_ISO_UTC,
        source_summary={"hypothesis": "src"},
        target_summary={"hypothesis": "tgt"},
    )
    return HandoffBlockedError(event)


# --- AC: every template renders -------------------------------------------


def test_every_template_renders_without_error() -> None:
    for (contract_name, rule_name), impact_text in IMPACT_TEMPLATES.items():
        rendered = render_impact_text(contract_name, rule_name, "src_agent", "tgt_agent")
        assert impact_text in rendered
        assert DEFAULT_IMPACT_FALLBACK not in rendered


# --- AC: in-place mutation, attached event unmodified ----------------------


def test_populate_mutates_in_place_and_leaves_event_unmodified() -> None:
    error = _blocked_error()
    assert error.impact_summary == ""
    before = error.violation_event.model_dump()

    populate_impact_summary(error)

    assert error.impact_summary != ""
    assert "required_fields" in error.impact_summary
    # The populator writes only the exception attribute; the carried
    # event must be byte-for-byte identical so exporters see it raw.
    assert error.violation_event.model_dump() == before


# --- AC: unknown combination falls back -----------------------------------


def test_unknown_combination_falls_back_to_default() -> None:
    rendered = render_impact_text("nonexistent_to_nowhere", "required_fields", "a", "b")
    assert DEFAULT_IMPACT_FALLBACK in rendered


# --- AC: rendered string carries every token ------------------------------


def test_rendered_string_contains_all_expected_tokens() -> None:
    rendered = render_impact_text(
        "researcher_to_summariser", "required_fields", "researcher", "summariser"
    )
    assert rendered.startswith("Handoff from researcher to summariser blocked:")
    assert "required_fields failed" in rendered
    assert "'researcher_to_summariser'" in rendered
    assert IMPACT_TEMPLATES[("researcher_to_summariser", "required_fields")] in rendered
    assert rendered.endswith(".")


# --- AC: demo-omission regression -----------------------------------------


def test_all_demo_combinations_have_entries() -> None:
    for combination in _DEMO_COMBINATIONS:
        assert combination in IMPACT_TEMPLATES, f"missing impact template for {combination}"


# --- Robustness: agent derivation from contract name ----------------------


def test_populate_derives_agents_from_contract_name() -> None:
    error = _blocked_error(contract_name="researcher_to_summariser")
    populate_impact_summary(error)
    assert error.impact_summary.startswith("Handoff from researcher to summariser blocked:")


def test_populate_target_keeps_nested_infix() -> None:
    # partition() on the first "_to_" keeps a target that itself
    # contains the infix rather than truncating it.
    error = _blocked_error(contract_name="a_to_b_to_c")
    populate_impact_summary(error)
    assert error.impact_summary.startswith("Handoff from a to b_to_c blocked:")


def test_populate_falls_back_to_generic_agents_without_infix() -> None:
    error = _blocked_error(contract_name="legacy_contract")
    populate_impact_summary(error)
    assert error.impact_summary.startswith("Handoff from upstream to downstream blocked:")


# --- Robustness: pure score-gate block (no rule failed) -------------------


def test_score_gate_only_block_uses_minimum_fidelity_and_fallback() -> None:
    error = _blocked_error(
        contract_name="researcher_to_summariser",
        rule_results=[
            _rule("required_fields", passed=True),
            _rule("preserved_entities", passed=True),
            _rule("forbidden_drops", passed=True),
        ],
    )
    populate_impact_summary(error)
    assert "minimum_fidelity failed" in error.impact_summary
    assert DEFAULT_IMPACT_FALLBACK in error.impact_summary


def test_empty_rule_results_uses_minimum_fidelity() -> None:
    # Empty rule_results is unreachable from Evaluator.evaluate() (it
    # always runs all three rules); it occurs only in PRC-014 fail-open
    # synthetic events or direct construction like this one. Built
    # synthetically here, never via the evaluator path, on purpose.
    error = _blocked_error(contract_name="researcher_to_summariser", rule_results=[])
    populate_impact_summary(error)
    assert "minimum_fidelity failed" in error.impact_summary


# --- Robustness: first failing rule wins ----------------------------------


def test_first_failing_rule_selected_in_evaluator_order() -> None:
    error = _blocked_error(
        contract_name="researcher_to_summariser",
        rule_results=[
            _rule("required_fields", passed=False),
            _rule("preserved_entities", passed=False),
            _rule("forbidden_drops", passed=True),
        ],
    )
    populate_impact_summary(error)
    assert "required_fields failed" in error.impact_summary
    assert "preserved_entities failed" not in error.impact_summary
    assert IMPACT_TEMPLATES[("researcher_to_summariser", "required_fields")] in error.impact_summary


# --- Module surface -------------------------------------------------------


def test_module_all_is_complete_and_sorted() -> None:
    import precept.integrations.langgraph.impact as mod

    assert mod.__all__ == sorted(mod.__all__)
    for name in mod.__all__:
        assert hasattr(mod, name), f"{name} in __all__ but not defined"
