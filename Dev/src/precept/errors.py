# SPDX-License-Identifier: MIT
"""Precept-specific exception types.

Every public API that performs validation wraps third-party exceptions
(notably ``pydantic.ValidationError`` and ``yaml.YAMLError``) and re-raises
as one of the exceptions defined here. See CLAUDE.md -> "Error handling"
for the wrap-at-module-boundary convention.

``ContractValidationError`` ships with PRC-006; ``HandoffBlockedError``
ships with PRC-013 and lives here so the LangGraph integration (PRC-014)
and the impact-summary populator (PRC-015) can both import it without
forming the circular dependency the original Rev 1 plan suffered from.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from pydantic import ValidationError as _PydanticValidationError

    from precept.types import ViolationEvent

__all__ = [
    "ContractValidationError",
    "ContractValidationIssue",
    "HandoffBlockedError",
]


class ContractValidationIssue(BaseModel):
    """One structured entry inside a ``ContractValidationError.details`` list.

    The triple of ``field_path`` + ``message`` + optional ``yaml_mark`` lets
    downstream consumers (the observatory, log formatters, PR review
    tooling) surface errors with precise location information without
    having to re-parse the underlying Pydantic error tree.
    """

    model_config = ConfigDict(extra="forbid")

    field_path: str
    """Dotted path to the offending field (e.g. ``"fields.min_fidelity"``)
    or ``"<yaml>"`` for YAML-syntax-level errors that cannot be tied to a
    single schema field."""

    message: str
    """Human-readable description of the issue."""

    yaml_mark: tuple[int, int] | None = None
    """1-indexed ``(line, column)`` position in the source YAML, when
    available. Only populated by the YAML loader for syntax errors;
    Pydantic-level schema errors do not carry YAML positions at v0 (see
    PRC-007a follow-up)."""


class ContractValidationError(Exception):
    """Raised when a ``HandoffContract`` fails schema or parse validation.

    The ``details`` list carries structured per-issue records so callers
    can present targeted errors. The exception message itself is a short
    human summary; callers wanting per-field detail should iterate
    ``details``.
    """

    def __init__(
        self,
        message: str,
        *,
        details: list[ContractValidationIssue] | None = None,
    ) -> None:
        super().__init__(message)
        self.details: list[ContractValidationIssue] = list(details) if details else []

    @classmethod
    def from_pydantic(
        cls,
        error: _PydanticValidationError,
        *,
        summary: str | None = None,
    ) -> ContractValidationError:
        """Build a ``ContractValidationError`` from a ``pydantic.ValidationError``.

        Each Pydantic error record becomes a ``ContractValidationIssue``.
        The ``yaml_mark`` field is left unset here; the YAML loader may
        enrich issues separately when it has YAML position information
        (PRC-007a).
        """

        details = [
            ContractValidationIssue(
                field_path=".".join(str(part) for part in err.get("loc", ())) or "<root>",
                message=str(err.get("msg", "")),
            )
            for err in error.errors()
        ]
        head = summary or "contract validation failed"
        return cls(f"{head} ({len(details)} issue(s))", details=details)


class HandoffBlockedError(Exception):
    """Raised when a ``mode='block'`` contract fails at handoff evaluation.

    The full :class:`precept.types.ViolationEvent` is attached so a
    supervisor (or any catching layer) can inspect per-rule and per-field
    detail without re-running the evaluator. ``impact_summary`` is a
    short human-readable narrative rendered by PRC-015's impact
    populator; it is **mutable by design** and intended to be populated
    post-construction.

    Post-construction-mutation contract (deliberate, documented):

    * Construction with ``impact_summary=""`` is the default. The error
      class itself has zero dependency on the impact-template module.
    * PRC-015's ``populate_impact_summary`` writes the rendered narrative
      onto an existing instance immediately before re-raise.
    * PRC-014's integration layer is the only caller that constructs
      and re-raises this class. The flow is:
      ``err = HandoffBlockedError(event)``  →
      ``populate_impact_summary(err, ...)`` →  ``raise err``.

    This shape exists to break the PRC-014 ⇄ PRC-015 circular dependency
    that an immutable, populator-required constructor would otherwise
    re-create. The mutability is **not** a license for arbitrary
    post-raise mutation by general-purpose callers; it is a single,
    bounded write performed by the integration layer.

    Callers wishing to bypass the populator (tests, non-LangGraph
    embedders) may pass ``impact_summary=...`` directly to the
    constructor. The error message exposed via :class:`Exception` args
    is a one-liner naming the failing contract; richer detail lives on
    the attached event.
    """

    def __init__(
        self,
        violation_event: ViolationEvent,
        *,
        impact_summary: str = "",
    ) -> None:
        super().__init__(f"Handoff blocked by contract {violation_event.contract_name!r}")
        self.violation_event: ViolationEvent = violation_event
        self.impact_summary: str = impact_summary
