# SPDX-License-Identifier: MIT
"""Precept-specific exception types.

Every public API that performs validation wraps third-party exceptions
(notably ``pydantic.ValidationError`` and ``yaml.YAMLError``) and re-raises
as one of the exceptions defined here. See CLAUDE.md -> "Error handling"
for the wrap-at-module-boundary convention.

Only ``ContractValidationError`` ships with PRC-006; further exceptions
(e.g. ``HandoffBlockedError``) land here in PRC-013.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from pydantic import ValidationError as _PydanticValidationError

__all__ = [
    "ContractValidationError",
    "ContractValidationIssue",
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
