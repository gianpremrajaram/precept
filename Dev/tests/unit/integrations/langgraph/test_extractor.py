# SPDX-License-Identifier: MIT
"""Unit tests for ``precept.integrations.langgraph.extractor`` (PRC-016).

Covers the two state-shape branches (mapping vs attribute), the
missing-field and present-but-``None`` distinction, string truncation,
non-string and nested-object pass-through, the metadata contract, and
the gating secret-leakage regression (uncontracted state is never read).

The shared ``valid_field_names`` Hypothesis strategy is imported via the
pytest ``pythonpath`` entry that makes ``tests/unit/contract`` importable
from any test module.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from hypothesis import given
from hypothesis import strategies as st
from pydantic import BaseModel
from strategies import valid_contract_names, valid_field_names

from precept.contract.schema import HandoffContract
from precept.integrations.langgraph.extractor import extract_payload
from precept.scoring.base import HandoffPayload

# --- Helpers --------------------------------------------------------------


def _contract(
    *,
    required: list[str] | None = None,
    preserved: list[str] | None = None,
) -> HandoffContract:
    preserved = preserved or []
    fields: dict[str, Any] = {
        "required_fields": required or [],
        "preserved_entities": preserved,
    }
    # Schema requires min_fidelity whenever preserved_entities is non-empty.
    if preserved:
        fields["min_fidelity"] = 0.5
    return HandoffContract(name="c", fields=fields)


@dataclass
class _DataclassState:
    hypothesis: str
    citations: list[str]
    secret: str


class _PydanticState(BaseModel):
    hypothesis: str
    citations: list[str]
    secret: str


class _FakeHumanMessage:
    """Stand-in for a LangGraph ``HumanMessage``.

    PRC-016 must not add ``langgraph`` / ``langchain-core`` as a runtime
    dependency (that is PRC-014's scope), and unit tests must stay
    I/O-free and fast, so we use a structurally similar local object
    rather than importing the real message type. The test asserts its
    content is never read because it lives in an *uncontracted* field -
    the message type is irrelevant to that guarantee.
    """

    def __init__(self, content: str) -> None:
        self.content = content
        self.type = "human"


# --- State-shape branches -------------------------------------------------


def test_dict_state_extracts_contracted_fields_only() -> None:
    contract = _contract(required=["hypothesis"], preserved=["author"])
    state = {
        "hypothesis": "renewables adoption is accelerating",
        "author": "Vella et al.",
        "internal_scratchpad": "ignore me",
    }

    payload = extract_payload(state, contract)

    assert set(payload.fields) == {"hypothesis", "author"}
    assert "internal_scratchpad" not in payload.fields
    assert payload.metadata["extraction_method"] == "mapping"
    assert payload.metadata["extracted_field_count"] == "2"
    assert payload.metadata["missing_field_count"] == "0"
    assert payload.metadata["truncated_field_count"] == "0"


def test_dataclass_state_extracts_via_attribute() -> None:
    contract = _contract(required=["hypothesis", "citations"])
    state = _DataclassState(hypothesis="h", citations=["c1", "c2"], secret="sk-should-not-be-read")

    payload = extract_payload(state, contract)

    assert payload.fields == {"hypothesis": "h", "citations": ["c1", "c2"]}
    assert payload.metadata["extraction_method"] == "attribute"


def test_pydantic_model_state_extracts_via_attribute() -> None:
    contract = _contract(required=["hypothesis", "citations"])
    state = _PydanticState(hypothesis="h", citations=["c1"], secret="sk-should-not-be-read")

    payload = extract_payload(state, contract)

    assert payload.fields == {"hypothesis": "h", "citations": ["c1"]}
    assert payload.metadata["extraction_method"] == "attribute"


def test_simplenamespace_state_uses_attribute_branch() -> None:
    contract = _contract(required=["hypothesis"])
    payload = extract_payload(SimpleNamespace(hypothesis="h"), contract)
    assert payload.fields == {"hypothesis": "h"}
    assert payload.metadata["extraction_method"] == "attribute"


# --- Missing vs present-but-None ------------------------------------------


def test_missing_field_recorded_as_none_and_counted() -> None:
    contract = _contract(required=["hypothesis", "citations"])
    payload = extract_payload({"hypothesis": "h"}, contract)

    assert payload.fields == {"hypothesis": "h", "citations": None}
    assert payload.metadata["missing_field_count"] == "1"
    assert payload.metadata["extracted_field_count"] == "1"


def test_present_none_value_is_extracted_not_missing() -> None:
    """A field explicitly set to ``None`` is present, not missing.

    Distinguishing this from an absent field is the reason the extractor
    uses a private sentinel rather than ``None`` as the not-found marker.
    """
    contract = _contract(required=["hypothesis", "citations"])

    dict_payload = extract_payload({"hypothesis": "h", "citations": None}, contract)
    assert dict_payload.fields == {"hypothesis": "h", "citations": None}
    assert dict_payload.metadata["missing_field_count"] == "0"
    assert dict_payload.metadata["extracted_field_count"] == "2"

    obj_payload = extract_payload(SimpleNamespace(hypothesis="h", citations=None), contract)
    assert obj_payload.metadata["missing_field_count"] == "0"
    assert obj_payload.metadata["extracted_field_count"] == "2"


# --- Truncation -----------------------------------------------------------


def test_long_string_truncated_with_suffix_and_counted() -> None:
    contract = _contract(required=["summary"])
    value = "x" * 5000

    payload = extract_payload(state={"summary": value}, contract=contract)

    out = payload.fields["summary"]
    assert isinstance(out, str)
    assert out.startswith("x" * 2000)
    assert out.endswith("... [truncated 3000 chars]")
    assert payload.metadata["truncated_field_count"] == "1"


def test_truncation_respects_custom_max_field_chars() -> None:
    contract = _contract(required=["summary"])
    payload = extract_payload({"summary": "y" * 100}, contract, max_field_chars=10)

    out = payload.fields["summary"]
    assert out == "y" * 10 + "... [truncated 90 chars]"
    assert payload.metadata["truncated_field_count"] == "1"


def test_short_string_not_truncated() -> None:
    contract = _contract(required=["summary"])
    payload = extract_payload({"summary": "short"}, contract)
    assert payload.fields["summary"] == "short"
    assert payload.metadata["truncated_field_count"] == "0"


# --- Non-string / nested pass-through (no recursion) ----------------------


def test_non_string_values_pass_through_untouched() -> None:
    contract = _contract(required=["count", "tags", "mapping"])
    state = {"count": 42, "tags": ["a", "b"], "mapping": {"k": "v"}}

    payload = extract_payload(state, contract)

    assert payload.fields["count"] == 42
    assert payload.fields["tags"] == ["a", "b"]
    assert payload.fields["mapping"] == {"k": "v"}
    assert payload.metadata["truncated_field_count"] == "0"


def test_nested_object_captured_as_is_without_recursion() -> None:
    nested = _PydanticState(hypothesis="h", citations=["c"], secret="s")
    contract = _contract(required=["payload"])

    payload = extract_payload({"payload": nested}, contract)

    # Same object, not a recursed/serialised copy.
    assert payload.fields["payload"] is nested


# --- Gating: uncontracted state is never read -----------------------------


def test_uncontracted_secret_never_extracted() -> None:
    """Gating regression (DEPENDENCIES.md 5.5 / 8.2).

    Secret-like values in *uncontracted* state must never appear in the
    resulting ``HandoffPayload`` - fields, metadata, or serialisation.
    """
    secret = "sk-live-DEADBEEF-super-secret-token"
    contract = _contract(required=["hypothesis"])
    state = {
        "hypothesis": "renewables adoption is accelerating",
        "api_key": secret,
        "db_password": secret,
        "nested": {"leaked": secret},
    }

    payload = extract_payload(state, contract)

    assert payload.fields == {"hypothesis": "renewables adoption is accelerating"}
    assert secret not in payload.model_dump_json()
    assert all(secret not in v for v in payload.metadata.values())


def test_uncontracted_message_content_never_read() -> None:
    secret = "sk-leaked-via-message-content"
    contract = _contract(required=["hypothesis"])
    state = {
        "hypothesis": "h",
        "messages": [_FakeHumanMessage(secret)],
    }

    payload = extract_payload(state, contract)

    assert "messages" not in payload.fields
    assert secret not in payload.model_dump_json()


# --- Union / dedup / metadata consistency ---------------------------------


def test_required_and_preserved_union_dedup_first_seen_order() -> None:
    contract = _contract(
        required=["hypothesis", "shared"],
        preserved=["shared", "author"],
    )
    state = {"hypothesis": "h", "shared": "s", "author": "a"}

    payload = extract_payload(state, contract)

    assert list(payload.fields) == ["hypothesis", "shared", "author"]
    assert payload.metadata["extracted_field_count"] == "3"


def test_metadata_counts_are_strings_and_sum_to_union_size() -> None:
    contract = _contract(required=["a", "b"], preserved=["c"])
    payload = extract_payload({"a": "x"}, contract)

    md = payload.metadata
    assert all(isinstance(v, str) for v in md.values())
    assert int(md["extracted_field_count"]) + int(md["missing_field_count"]) == 3


def test_empty_contract_yields_empty_payload() -> None:
    """Scaffold/observe-only contract (ADR 0001): nothing to extract."""
    payload = extract_payload({"anything": "ignored"}, _contract())
    assert payload.fields == {}
    assert payload.metadata["extracted_field_count"] == "0"
    assert payload.metadata["missing_field_count"] == "0"


# --- Property-based -------------------------------------------------------

_field_lists = st.lists(valid_field_names, unique=True, max_size=6)

# Identifier-safe, non-dunder names for the attribute-state property test:
# ``setattr`` on a ``SimpleNamespace`` rejects readonly dunders such as
# ``__dict__``. ``required`` names below are unaffected because they only
# reach ``getattr(obj, name, _MISSING)``, which is safe for any string.
_safe_attr_names = st.from_regex(r"[a-z][a-z0-9_]{0,15}", fullmatch=True)


@given(
    name=valid_contract_names,
    required=_field_lists,
    preserved=_field_lists,
    state=st.dictionaries(valid_field_names, st.text(max_size=20), max_size=10),
)
def test_property_fields_count_equals_union_size_dict_state(
    name: str,
    required: list[str],
    preserved: list[str],
    state: dict[str, str],
) -> None:
    """AC property: ``len(fields)`` equals the union size of required and
    preserved field names, for arbitrary dict states and contracts,
    regardless of overlap with state."""
    fields: dict[str, Any] = {
        "required_fields": required,
        "preserved_entities": preserved,
    }
    if preserved:
        fields["min_fidelity"] = 0.5
    contract = HandoffContract(name=name, fields=fields)

    payload = extract_payload(state, contract)

    expected = len(set(required) | set(preserved))
    assert len(payload.fields) == expected


@given(
    required=_field_lists,
    state_items=st.dictionaries(_safe_attr_names, st.text(max_size=20), max_size=10),
)
def test_property_invariant_holds_for_attribute_state(
    required: list[str],
    state_items: dict[str, str],
) -> None:
    """Extends the AC property test (which scopes to dict states) to the
    attribute branch, exercising the ``getattr`` path with the same
    invariant. Deliberate over-AC hardening: the resolver branches on
    state shape, so the property should hold for both shapes."""
    contract = HandoffContract(name="c", fields={"required_fields": required})

    obj = SimpleNamespace()
    for k, v in state_items.items():
        setattr(obj, k, v)

    payload = extract_payload(obj, contract)

    assert len(payload.fields) == len(set(required))
    assert payload.metadata["extraction_method"] == "attribute"
    assert isinstance(payload, HandoffPayload)
