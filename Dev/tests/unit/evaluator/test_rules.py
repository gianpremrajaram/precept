# SPDX-License-Identifier: Apache-2.0
"""Unit tests for ``precept.evaluator.rules`` (PRC-012).

Covers ``RuleResult`` construction, the three rule functions
(``required_fields_rule``, ``preserved_entities_rule``,
``forbidden_drops_rule``), the documented per-rule ``details`` shapes,
violation-message templates, and property-based robustness.

The shared ``valid_field_names`` Hypothesis strategy is imported via
the pytest ``pythonpath`` entry that makes ``tests/unit/contract``
importable from any test module.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError
from strategies import valid_field_names

from precept.evaluator.rules import (
    RuleResult,
    forbidden_drops_rule,
    preserved_entities_rule,
    required_fields_rule,
)
from precept.scoring.base import HandoffPayload

# --- Fixtures / helpers ---------------------------------------------------


def _payload(**fields: object) -> HandoffPayload:
    return HandoffPayload(fields=dict(fields))


# --- RuleResult model -----------------------------------------------------


def test_rule_result_accepts_fully_populated_instance() -> None:
    result = RuleResult(
        rule_name="required_fields",
        passed=False,
        details={"required": ["a"], "missing": ["a"]},
        violation_message="Required field 'a' missing in target payload",
    )
    assert result.rule_name == "required_fields"
    assert result.passed is False
    assert result.details == {"required": ["a"], "missing": ["a"]}
    assert result.violation_message is not None


def test_rule_result_defaults() -> None:
    result = RuleResult(rule_name="required_fields", passed=True)
    assert result.details == {}
    assert result.violation_message is None


def test_rule_result_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        RuleResult(
            rule_name="required_fields",
            passed=True,
            unexpected="boom",  # type: ignore[call-arg]
        )


# --- required_fields_rule -------------------------------------------------


def test_required_fields_rule_all_present_passes() -> None:
    src = _payload()
    tgt = _payload(a="x", b="y")
    result = required_fields_rule(src, tgt, ["a", "b"])

    assert result.passed is True
    assert result.violation_message is None
    assert result.details == {"required": ["a", "b"], "missing": []}
    assert result.rule_name == "required_fields"


def test_required_fields_rule_single_missing_fails_with_named_field() -> None:
    src = _payload()
    tgt = _payload(a="x")  # b missing
    result = required_fields_rule(src, tgt, ["a", "b"])

    assert result.passed is False
    assert result.details == {"required": ["a", "b"], "missing": ["b"]}
    assert result.violation_message == "Required field 'b' missing in target payload"


def test_required_fields_rule_multiple_missing_uses_plural() -> None:
    src = _payload()
    tgt = _payload(a="x")  # b and c missing
    result = required_fields_rule(src, tgt, ["a", "b", "c"])

    assert result.passed is False
    assert result.details["missing"] == ["b", "c"]
    assert result.violation_message == "Required fields 'b', 'c' missing in target payload"


def test_required_fields_rule_preserves_required_order_in_details() -> None:
    src = _payload()
    tgt = _payload(a="x")
    result = required_fields_rule(src, tgt, ["c", "a", "b"])
    # required passes through in original order; missing follows scan order.
    assert result.details["required"] == ["c", "a", "b"]
    assert result.details["missing"] == ["c", "b"]


def test_required_fields_rule_empty_required_always_passes() -> None:
    src = _payload(anything="here")
    tgt = _payload()
    result = required_fields_rule(src, tgt, [])

    assert result.passed is True
    assert result.details == {"required": [], "missing": []}
    assert result.violation_message is None


def test_required_fields_rule_ignores_source_payload() -> None:
    """``source`` is part of the uniform signature but unused here."""
    tgt = _payload(a="x", b="y")
    a = required_fields_rule(_payload(), tgt, ["a", "b"])
    b = required_fields_rule(_payload(z="ignored"), tgt, ["a", "b"])
    assert a.model_dump() == b.model_dump()


# --- preserved_entities_rule ---------------------------------------------


def test_preserved_entities_rule_present_in_both_passes() -> None:
    src = _payload(text="Smith reported elevated levels.")
    tgt = _payload(text="The Smith study confirmed elevated levels.")
    result = preserved_entities_rule(src, tgt, ["Smith"])

    assert result.passed is True
    assert result.details == {"entities": ["Smith"], "missing": []}
    assert result.violation_message is None


def test_preserved_entities_rule_in_source_only_fails() -> None:
    src = _payload(text="Smith reported elevated levels.")
    tgt = _payload(text="A study confirmed elevated levels.")
    result = preserved_entities_rule(src, tgt, ["Smith"])

    assert result.passed is False
    assert result.details["missing"] == ["Smith"]
    assert (
        result.violation_message
        == "Preserved entity 'Smith' present in source but missing in target"
    )


def test_preserved_entities_rule_entity_not_in_source_is_vacuous_pass() -> None:
    """Entity NOT in source -> vacuous pass.

    Mirrors ``forbidden_drops_rule`` semantics: target-only fields are
    not violations, and entities never present in the source cannot
    have been dropped from it.
    """
    src = _payload(text="A nondescript handover note.")
    tgt = _payload(text="An equally nondescript downstream note.")
    result = preserved_entities_rule(src, tgt, ["Smith"])

    assert result.passed is True
    assert result.details["missing"] == []
    assert result.violation_message is None


def test_preserved_entities_rule_case_insensitive_source_upper_target_lower() -> None:
    src = _payload(text="SMITH led the study.")
    tgt = _payload(text="smith confirmed the result.")
    result = preserved_entities_rule(src, tgt, ["Smith"])
    assert result.passed is True


def test_preserved_entities_rule_case_insensitive_source_lower_target_upper() -> None:
    src = _payload(text="smith led the study.")
    tgt = _payload(text="SMITH confirmed the result.")
    result = preserved_entities_rule(src, tgt, ["Smith"])
    assert result.passed is True


def test_preserved_entities_rule_empty_entities_always_passes() -> None:
    src = _payload(text="Smith reported elevated levels.")
    tgt = _payload(text="A study confirmed elevated levels.")
    result = preserved_entities_rule(src, tgt, [])
    assert result.passed is True
    assert result.details == {"entities": [], "missing": []}


def test_preserved_entities_rule_stringifies_non_string_fields() -> None:
    src = _payload(meta={"author": "Smith"})
    tgt = _payload(meta="A handoff note about Smith.")
    result = preserved_entities_rule(src, tgt, ["Smith"])
    assert result.passed is True


def test_preserved_entities_rule_mixed_entities_only_failing_in_missing() -> None:
    src = _payload(text="Smith and Wang reported high values.")
    tgt = _payload(text="Smith confirmed.")  # Wang dropped
    result = preserved_entities_rule(src, tgt, ["Smith", "Wang"])

    assert result.passed is False
    assert result.details["missing"] == ["Wang"]
    assert "Wang" in (result.violation_message or "")
    assert "Smith" not in (result.violation_message or "")


def test_preserved_entities_rule_multiple_missing_uses_plural() -> None:
    src = _payload(text="Smith, Wang, and Chen reported high values.")
    tgt = _payload(text="A study reported high values.")  # all three dropped
    result = preserved_entities_rule(src, tgt, ["Smith", "Wang", "Chen"])

    assert result.passed is False
    assert result.details["missing"] == ["Smith", "Wang", "Chen"]
    assert (
        result.violation_message
        == "Preserved entities 'Smith', 'Wang', 'Chen' present in source but missing in target"
    )


def test_preserved_entities_rule_does_not_consult_raw() -> None:
    """The rule reads ``.fields`` only; ``.raw`` is ignored.

    Set ``.fields`` to omit the entity but pack it into ``.raw``; rule
    must still report missing because ``.raw`` is not part of the
    haystack.
    """
    src = _payload(text="Smith led the study.")
    tgt = HandoffPayload(
        fields={"text": "A study confirmed."},
        raw="Smith was the lead.",
    )
    result = preserved_entities_rule(src, tgt, ["Smith"])
    assert result.passed is False
    assert result.details["missing"] == ["Smith"]


def test_preserved_entities_rule_does_not_match_across_field_boundaries() -> None:
    """Newline-joined haystack prevents adjacent fields colliding into a spurious match."""
    src = _payload(a="...Smith", b="Doe...")
    tgt = _payload(a="Doe...", b="...Smith")
    result = preserved_entities_rule(src, tgt, ["SmithDoe"])
    assert result.passed is True  # neither side actually contains "SmithDoe"


# --- forbidden_drops_rule -------------------------------------------------


def test_forbidden_drops_rule_present_in_both_passes() -> None:
    src = _payload(citations="Smith 2024", hypothesis="x")
    tgt = _payload(citations="Smith 2024", hypothesis="x")
    result = forbidden_drops_rule(src, tgt, ["citations"])

    assert result.passed is True
    assert result.details == {"forbidden": ["citations"], "dropped": []}
    assert result.violation_message is None


def test_forbidden_drops_rule_present_in_source_only_fails() -> None:
    src = _payload(citations="Smith 2024")
    tgt = _payload()  # citations dropped
    result = forbidden_drops_rule(src, tgt, ["citations"])

    assert result.passed is False
    assert result.details == {"forbidden": ["citations"], "dropped": ["citations"]}
    assert (
        result.violation_message
        == "Forbidden drop: field 'citations' present in source but absent in target"
    )


def test_forbidden_drops_rule_present_in_target_only_passes() -> None:
    src = _payload()
    tgt = _payload(citations="Smith 2024")
    result = forbidden_drops_rule(src, tgt, ["citations"])
    assert result.passed is True
    assert result.details["dropped"] == []


def test_forbidden_drops_rule_absent_from_both_passes() -> None:
    src = _payload(other="x")
    tgt = _payload(other="y")
    result = forbidden_drops_rule(src, tgt, ["citations"])
    assert result.passed is True


def test_forbidden_drops_rule_mixed_only_dropped_in_details() -> None:
    src = _payload(citations="x", figures="y", hypothesis="z")
    tgt = _payload(hypothesis="z")  # citations and figures dropped
    result = forbidden_drops_rule(src, tgt, ["citations", "figures", "hypothesis"])

    assert result.passed is False
    assert result.details["dropped"] == ["citations", "figures"]
    assert (
        result.violation_message
        == "Forbidden drops: fields 'citations', 'figures' present in source but absent in target"
    )


def test_forbidden_drops_rule_empty_forbidden_always_passes() -> None:
    src = _payload(any="thing")
    tgt = _payload()
    result = forbidden_drops_rule(src, tgt, [])
    assert result.passed is True
    assert result.details == {"forbidden": [], "dropped": []}


# --- AC violation_message exemplar ----------------------------------------


def test_ac_example_message_for_missing_hypothesis() -> None:
    """Exact wording from the PRC-012 acceptance criteria."""
    src = _payload(hypothesis="x")
    tgt = _payload()
    result = required_fields_rule(src, tgt, ["hypothesis"])
    assert result.violation_message == "Required field 'hypothesis' missing in target payload"


# --- Property-based: rules never raise ------------------------------------


_loose_value = st.one_of(
    st.text(),
    st.integers(),
    st.floats(allow_nan=False, allow_infinity=False),
    st.booleans(),
    st.lists(st.text(), max_size=3),
    st.none(),
)


@given(
    src_fields=st.dictionaries(st.text(), _loose_value, max_size=5),
    tgt_fields=st.dictionaries(st.text(), _loose_value, max_size=5),
    items=st.lists(st.text(), max_size=10),
)
def test_rules_never_raise_on_arbitrary_input(
    src_fields: dict[str, object],
    tgt_fields: dict[str, object],
    items: list[str],
) -> None:
    src = HandoffPayload(fields=src_fields)
    tgt = HandoffPayload(fields=tgt_fields)
    # Each rule must return a RuleResult, never raise.
    assert isinstance(required_fields_rule(src, tgt, items), RuleResult)
    assert isinstance(preserved_entities_rule(src, tgt, items), RuleResult)
    assert isinstance(forbidden_drops_rule(src, tgt, items), RuleResult)


# --- Property-based: required_fields_rule passes when target has them -----


@given(field_names=st.lists(valid_field_names, min_size=1, max_size=8, unique=True))
def test_required_fields_rule_passes_when_target_has_them(field_names: list[str]) -> None:
    src = _payload()
    tgt = HandoffPayload(fields=dict.fromkeys(field_names, "x"))
    result = required_fields_rule(src, tgt, field_names)
    assert result.passed is True
    assert result.details["missing"] == []
