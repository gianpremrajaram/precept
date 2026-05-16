# SPDX-License-Identifier: MIT
"""Decorator frontend: attaches a ``HandoffContract`` to a handoff function.

One of two v0 frontends declared in ADR 0001 (the other is the YAML loader,
PRC-007). Both produce the same ``HandoffContract`` IR and surface schema
errors through ``precept.errors.ContractValidationError``; the evaluator
(PRC-013) consumes only the IR and never sees which frontend produced it.

Scope at v0 (PRC-008): the decorator is a *pure metadata attachment*
mechanism. It validates the contract at decoration time and stores it on
the function as ``__precept_contract__``; it does **not** evaluate the
contract at call time. Runtime evaluation is wired by the LangGraph
integration (PRC-014), which reads ``__precept_contract__``.

Sync functions only. Async decoration introduces signature-preservation
and awaitable-wrapping edge cases that are out of scope for v0; a coroutine
function raises ``TypeError`` with guidance. Tracked as a Phase 2
enhancement (DEPENDENCIES.md technical-debt ledger, "Decorator frontend
sync-only").

The kwarg ``required`` maps to the IR field ``required_fields``; this is a
deliberate developer-ergonomics choice. Field values flow into the IR as a
nested ``fields`` mapping passed to ``HandoffContract``, so the single
``HandoffContract.__init__`` validation boundary converts any
``pydantic.ValidationError`` into ``ContractValidationError`` uniformly
(matching the construction path documented in ``contract.schema``).
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from typing import Any, Literal, TypeVar, cast

from precept.contract.schema import HandoffContract

__all__ = ["handoff_contract"]

F = TypeVar("F", bound=Callable[..., Any])

ASYNC_REJECTION_MESSAGE = (
    "Async function decoration is not supported in v0.1.0. Use "
    "precept.load_contract() or HandoffContract(...) directly with your "
    "async function. Tracked: Phase 2 enhancement."
)
"""Verbatim guidance raised when ``@handoff_contract(...)`` decorates a
coroutine function. Named for testability."""

BARE_FORM_MESSAGE = (
    "@handoff_contract must be called with arguments, e.g. "
    '@handoff_contract(name="researcher_to_summariser", required=[...]). '
    "The bare @handoff_contract form (no parentheses) is not supported."
)
"""Verbatim guidance raised when the decorator is applied bare (no call).
Named for testability."""

MISSING_NAME_MESSAGE = (
    "@handoff_contract requires a name, e.g. "
    '@handoff_contract(name="researcher_to_summariser", required=[...]). '
    "name identifies the contract in the registry and in violation events."
)
"""Verbatim guidance raised when ``name`` is omitted (or ``None``).

A missing required argument is an API-usage error, categorically distinct
from a contract-content error; it raises ``TypeError`` here rather than
falling through to a ``ContractValidationError`` from the schema's
``Field required``. Named for testability."""


def handoff_contract(
    _fn: Callable[..., Any] | None = None,
    *,
    name: str | None = None,
    required: list[str] | None = None,
    preserved_entities: list[str] | None = None,
    min_fidelity: float | None = None,
    forbidden_drops: list[str] | None = None,
    mode: Literal["block", "warn"] | None = None,
    description: str | None = None,
    version: str | None = None,
) -> Callable[[F], F]:
    """Attach a validated ``HandoffContract`` to a sync handoff function.

    Use the call form only::

        @handoff_contract(
            name="researcher_to_summariser",
            required=["hypothesis", "citations"],
            preserved_entities=["primary_source"],
            min_fidelity=0.75,
            forbidden_drops=["uncertainty_bounds"],
            mode="block",
        )
        def handoff_to_summariser(state): ...

    The decorated function is unchanged at call time; the contract is
    retrievable as ``handoff_to_summariser.__precept_contract__`` (a
    ``HandoffContract``). The integration layer (PRC-014) consumes that
    attribute to perform evaluation.

    Raises:
        TypeError: if applied bare (``@handoff_contract`` without a call),
            if ``name`` is omitted (a required argument; this is an
            API-usage error, kept distinct from a contract-content error),
            or if applied to a coroutine function (async is out of scope
            at v0).
        precept.errors.ContractValidationError: if the supplied fields do
            not satisfy the ``HandoffContract`` schema. Raised at
            *decoration time*, not call time.
    """

    if _fn is not None:
        raise TypeError(BARE_FORM_MESSAGE)
    if name is None:
        raise TypeError(MISSING_NAME_MESSAGE)

    fields_data: dict[str, Any] = {}
    if required is not None:
        fields_data["required_fields"] = required
    if preserved_entities is not None:
        fields_data["preserved_entities"] = preserved_entities
    if min_fidelity is not None:
        fields_data["min_fidelity"] = min_fidelity
    if forbidden_drops is not None:
        fields_data["forbidden_drops"] = forbidden_drops

    # name is guaranteed non-None by the guard above (mypy narrows it).
    contract_data: dict[str, Any] = {"fields": fields_data, "name": name}
    if mode is not None:
        contract_data["mode"] = mode
    if description is not None:
        contract_data["description"] = description
    if version is not None:
        contract_data["version"] = version

    # Single validation boundary: a nested ``fields`` mapping routes
    # ContractFields validation through HandoffContract.__init__, which is
    # the only place pydantic.ValidationError is wrapped into
    # ContractValidationError. Raised here, at decoration time.
    contract = HandoffContract(**contract_data)

    def decorator(func: F) -> F:
        if inspect.iscoroutinefunction(func):
            raise TypeError(ASYNC_REJECTION_MESSAGE)

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)

        # Dynamic marker attribute the PRC-014 integration layer reads.
        # mypy --strict cannot know a Callable carries it; the targeted
        # ignore is narrower (and ruff-clean) than a setattr call.
        wrapper.__precept_contract__ = contract  # type: ignore[attr-defined]
        return cast(F, wrapper)

    return decorator
