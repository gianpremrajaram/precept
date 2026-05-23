# SPDX-License-Identifier: MIT
"""Unit tests for ``precept.contract.decorator`` (PRC-008).

The decorator is a pure metadata-attachment mechanism at v0: it validates
the contract at decoration time and attaches it as ``__precept_contract__``
without altering call-time behaviour. These tests cover signature
preservation, the attached IR, decoration-time validation, and the two
``TypeError`` guard rails (async function, bare form).
"""

from __future__ import annotations

import inspect

import pytest

from precept.contract.decorator import (
    ASYNC_REJECTION_MESSAGE,
    BARE_FORM_MESSAGE,
    MISSING_NAME_MESSAGE,
    handoff_contract,
)
from precept.contract.schema import HandoffContract
from precept.errors import ContractValidationError

# --- Signature / return-type preservation --------------------------------


def test_decorated_sync_function_retains_signature_and_return() -> None:
    @handoff_contract(name="researcher_to_summariser", required=["hypothesis"])
    def handoff(state: dict[str, int], *, flag: bool = False) -> int:
        """Original docstring."""
        return state["x"] + (1 if flag else 0)

    def reference(state: dict[str, int], *, flag: bool = False) -> int:
        return 0

    assert inspect.signature(handoff) == inspect.signature(reference)
    assert handoff.__name__ == "handoff"
    assert handoff.__doc__ == "Original docstring."
    assert handoff({"x": 41}) == 41
    assert handoff({"x": 41}, flag=True) == 42


# --- Attached IR ----------------------------------------------------------


def test_precept_contract_attribute_is_valid_handoff_contract() -> None:
    @handoff_contract(
        name="researcher_to_summariser",
        required=["hypothesis", "citations"],
        preserved_entities=["primary_source"],
        min_fidelity=0.75,
        forbidden_drops=["uncertainty_bounds"],
        mode="block",
        description="research to summariser",
        version="1.0",
    )
    def handoff(state: dict[str, object]) -> dict[str, object]:
        return state

    contract = handoff.__precept_contract__  # type: ignore[attr-defined]
    assert isinstance(contract, HandoffContract)
    assert contract.name == "researcher_to_summariser"
    assert contract.mode == "block"
    assert contract.version == "1.0"
    assert contract.description == "research to summariser"
    # Ergonomic kwarg `required` maps to IR field `required_fields`.
    assert contract.fields.required_fields == ["hypothesis", "citations"]
    assert contract.fields.preserved_entities == ["primary_source"]
    assert contract.fields.min_fidelity == 0.75
    assert contract.fields.forbidden_drops == ["uncertainty_bounds"]


def test_omitted_kwargs_fall_back_to_schema_defaults() -> None:
    @handoff_contract(name="minimal")
    def handoff(state: dict[str, object]) -> dict[str, object]:
        return state

    contract = handoff.__precept_contract__  # type: ignore[attr-defined]
    assert contract.version == "0.1"
    assert contract.mode == "warn"
    assert contract.description is None
    assert contract.fields.required_fields == []
    assert contract.fields.preserved_entities == []
    assert contract.fields.min_fidelity is None
    assert contract.fields.forbidden_drops == []


# --- Decoration-time validation ------------------------------------------


def test_invalid_kwarg_raises_contract_validation_error_at_decoration() -> None:
    # The factory builds (and validates) the HandoffContract before it
    # returns the inner decorator, so the error surfaces here, not at call
    # time and not at function definition.
    with pytest.raises(ContractValidationError):
        handoff_contract(name="researcher_to_summariser", min_fidelity=2.0)


def test_invalid_name_raises_contract_validation_error() -> None:
    with pytest.raises(ContractValidationError):
        handoff_contract(name="Has Spaces And Caps", required=["x"])


# --- Guard rails ----------------------------------------------------------


def test_async_function_raises_typeerror_with_documented_message() -> None:
    decorator = handoff_contract(name="researcher_to_summariser")

    async def async_handoff(state: dict[str, object]) -> dict[str, object]:
        return state

    with pytest.raises(TypeError) as exc_info:
        decorator(async_handoff)
    assert str(exc_info.value) == ASYNC_REJECTION_MESSAGE


def test_bare_form_raises_typeerror_with_clear_message() -> None:
    def plain(state: dict[str, object]) -> dict[str, object]:
        return state

    # Bare `@handoff_contract` is sugar for `handoff_contract(plain)`.
    with pytest.raises(TypeError) as exc_info:
        handoff_contract(plain)
    assert str(exc_info.value) == BARE_FORM_MESSAGE


def test_missing_name_raises_typeerror_not_contract_validation_error() -> None:
    # Omitting the required `name` is an API-usage error: a clear
    # TypeError, not a pydantic "Field required" wrapped as
    # ContractValidationError. Contract-content validation stays routed
    # through HandoffContract; argument presence does not.
    with pytest.raises(TypeError) as exc_info:
        handoff_contract(required=["hypothesis"])
    assert str(exc_info.value) == MISSING_NAME_MESSAGE
