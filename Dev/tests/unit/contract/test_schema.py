# SPDX-License-Identifier: Apache-2.0
"""Unit tests for ``precept.contract.schema``.

Tests exercise the full schema exclusively through ``HandoffContract``
(the public construction path), so the ``__init__`` wrapper converts
Pydantic's native ``ValidationError`` into ``ContractValidationError``
uniformly. ``ContractFields`` is accessed via nested-dict input to
``HandoffContract``.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from strategies import valid_contract_names, valid_min_fidelity

from precept.contract.schema import NAME_PATTERN, ContractFields, HandoffContract
from precept.errors import ContractValidationError, ContractValidationIssue

# --- Valid construction ---------------------------------------------------


def test_valid_contract_with_all_fields_populated() -> None:
    c = HandoffContract(
        name="researcher_to_summariser",
        version="1.0",
        mode="block",
        description="Research to summariser handoff",
        fields={
            "required_fields": ["hypothesis", "citations"],
            "preserved_entities": ["primary_source"],
            "min_fidelity": 0.75,
            "forbidden_drops": ["uncertainty_bounds"],
        },
        metadata={"owner": "research-team", "tier": "critical"},
    )
    assert c.name == "researcher_to_summariser"
    assert c.mode == "block"
    assert c.fields.required_fields == ["hypothesis", "citations"]
    assert c.fields.min_fidelity == 0.75
    assert c.metadata == {"owner": "research-team", "tier": "critical"}


def test_defaults_applied_when_only_required_fields_given() -> None:
    c = HandoffContract(name="minimal", fields={})
    assert c.version == "0.1"
    assert c.mode == "warn"
    assert c.description is None
    assert c.metadata == {}
    assert c.fields.required_fields == []
    assert c.fields.preserved_entities == []
    assert c.fields.min_fidelity is None
    assert c.fields.forbidden_drops == []


def test_empty_contract_is_permitted() -> None:
    """ADR 0001: all-empty contracts are valid scaffold / observe-only contracts."""
    c = HandoffContract(name="scaffold", fields={})
    assert c.fields.required_fields == []
    assert c.fields.preserved_entities == []
    assert c.fields.forbidden_drops == []
    assert c.fields.min_fidelity is None


# --- extra="forbid" -------------------------------------------------------


def test_unknown_top_level_field_rejected() -> None:
    with pytest.raises(ContractValidationError):
        HandoffContract(name="x", fields={}, bogus="anything")


def test_unknown_nested_field_rejected() -> None:
    with pytest.raises(ContractValidationError):
        HandoffContract(name="x", fields={"required_fields": [], "bogus": "x"})


# --- name regex -----------------------------------------------------------


@pytest.mark.parametrize(
    "bad_name",
    [
        "Alpha",  # uppercase
        "1alpha",  # digit start
        "alpha beta",  # space
        "alpha!",  # punctuation
        "",  # empty
        "-alpha",  # hyphen start
        "_alpha",  # underscore start
    ],
)
def test_invalid_names_rejected(bad_name: str) -> None:
    with pytest.raises(ContractValidationError):
        HandoffContract(name=bad_name, fields={})


@pytest.mark.parametrize(
    "good_name",
    ["a", "alpha", "alpha-beta", "alpha_beta", "a1", "x-y-z_0"],
)
def test_valid_names_accepted(good_name: str) -> None:
    c = HandoffContract(name=good_name, fields={})
    assert c.name == good_name


# --- mode literal ---------------------------------------------------------


def test_invalid_mode_rejected() -> None:
    with pytest.raises(ContractValidationError):
        HandoffContract(name="x", mode="ignore", fields={})


# --- min_fidelity ---------------------------------------------------------


@pytest.mark.parametrize("bad_value", [-0.1, 1.1, -1.0, 2.0])
def test_min_fidelity_out_of_range_rejected(bad_value: float) -> None:
    with pytest.raises(ContractValidationError):
        HandoffContract(
            name="x",
            fields={"preserved_entities": ["a"], "min_fidelity": bad_value},
        )


def test_min_fidelity_non_numeric_rejected() -> None:
    with pytest.raises(ContractValidationError):
        HandoffContract(
            name="x",
            fields={"preserved_entities": ["a"], "min_fidelity": "not-a-float"},
        )


def test_min_fidelity_required_when_preserved_entities_non_empty() -> None:
    with pytest.raises(ContractValidationError) as exc_info:
        HandoffContract(name="x", fields={"preserved_entities": ["a"]})
    assert "min_fidelity" in str(exc_info.value) or any(
        "min_fidelity" in d.message for d in exc_info.value.details
    )


def test_min_fidelity_optional_when_preserved_entities_empty() -> None:
    c = HandoffContract(name="x", fields={"required_fields": ["a"]})
    assert c.fields.min_fidelity is None


# --- list-intersection rules ---------------------------------------------


def test_required_fields_forbidden_drops_intersection_rejected() -> None:
    with pytest.raises(ContractValidationError) as exc_info:
        HandoffContract(
            name="x",
            fields={
                "required_fields": ["x", "y"],
                "forbidden_drops": ["y", "z"],
            },
        )
    msg = str(exc_info.value) + " ".join(d.message for d in exc_info.value.details)
    assert "intersect" in msg or "overlap" in msg


def test_required_fields_preserved_entities_intersection_permitted() -> None:
    """Per ADR: these are not inherently contradictory; allow the overlap."""
    c = HandoffContract(
        name="x",
        fields={
            "required_fields": ["x"],
            "preserved_entities": ["x"],
            "min_fidelity": 0.5,
        },
    )
    assert "x" in c.fields.required_fields
    assert "x" in c.fields.preserved_entities


def test_preserved_entities_forbidden_drops_intersection_permitted() -> None:
    """Per ADR: these are not inherently contradictory; allow the overlap."""
    c = HandoffContract(
        name="x",
        fields={
            "preserved_entities": ["x"],
            "min_fidelity": 0.5,
            "forbidden_drops": ["x"],
        },
    )
    assert "x" in c.fields.preserved_entities
    assert "x" in c.fields.forbidden_drops


# --- duplicates -----------------------------------------------------------


@pytest.mark.parametrize(
    "field_name, fields",
    [
        ("required_fields", {"required_fields": ["a", "a"]}),
        (
            "preserved_entities",
            {"preserved_entities": ["a", "a"], "min_fidelity": 0.5},
        ),
        ("forbidden_drops", {"forbidden_drops": ["a", "a"]}),
    ],
)
def test_duplicates_rejected(field_name: str, fields: dict[str, object]) -> None:
    with pytest.raises(ContractValidationError) as exc_info:
        HandoffContract(name="x", fields=fields)
    joined = str(exc_info.value) + " ".join(d.message for d in exc_info.value.details)
    assert field_name in joined or "duplicate" in joined


# --- metadata typing ------------------------------------------------------


def test_metadata_rejects_non_string_values() -> None:
    with pytest.raises(ContractValidationError):
        HandoffContract(name="x", fields={}, metadata={"owner": 42})


# --- error structure ------------------------------------------------------


def test_contract_validation_error_has_structured_details() -> None:
    with pytest.raises(ContractValidationError) as exc_info:
        HandoffContract(name="Invalid", fields={})
    err = exc_info.value
    assert err.details, "ContractValidationError must expose structured details"
    for issue in err.details:
        assert isinstance(issue, ContractValidationIssue)
        assert issue.field_path
        assert issue.message


# --- NAME_PATTERN export --------------------------------------------------


def test_name_pattern_is_exported_and_matches_regex() -> None:
    assert NAME_PATTERN.match("ok_name-42")
    assert not NAME_PATTERN.match("Bad Name")


# --- property-based -------------------------------------------------------


@given(name=valid_contract_names)
def test_any_regex_matching_name_accepted(name: str) -> None:
    c = HandoffContract(name=name, fields={})
    assert c.name == name


@given(fidelity=valid_min_fidelity)
def test_any_float_in_range_accepted_for_min_fidelity(fidelity: float) -> None:
    c = HandoffContract(
        name="x",
        fields={"preserved_entities": ["a"], "min_fidelity": fidelity},
    )
    assert c.fields.min_fidelity == fidelity


# --- ContractFields direct instantiation ---------------------------------


def test_contract_fields_default_construction() -> None:
    cf = ContractFields()
    assert cf.required_fields == []
    assert cf.preserved_entities == []
    assert cf.forbidden_drops == []
    assert cf.min_fidelity is None
