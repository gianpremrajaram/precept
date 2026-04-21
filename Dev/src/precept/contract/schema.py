# SPDX-License-Identifier: MIT
"""Canonical intermediate representation for Precept contracts.

``HandoffContract`` is the single source of truth for contract declarations.
Both the YAML loader (``precept.contract.yaml_loader``, PRC-007) and the
decorator frontend (``precept.contract.decorator``, PRC-008) produce
``HandoffContract`` instances; the evaluator (PRC-013) consumes only
``HandoffContract``.

See ``docs/adr/0001-contract-ir.md`` for the architectural rationale and
the empty-contract (observe-only scaffold) semantics.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)

from precept.errors import ContractValidationError

__all__ = [
    "NAME_PATTERN",
    "ContractFields",
    "HandoffContract",
]

NAME_PATTERN: re.Pattern[str] = re.compile(r"^[a-z][a-z0-9_-]*$")
"""Regex a ``HandoffContract.name`` must match.

Lowercase-start, URL- and OTel-attribute-safe. See PRC-006 acceptance
criteria for rationale.
"""


class ContractFields(BaseModel):
    """Rule-carrying portion of a ``HandoffContract``.

    All three list fields default to empty; an all-empty ``ContractFields``
    represents a scaffold / observe-only contract (see ADR 0001).
    """

    model_config = ConfigDict(extra="forbid")

    required_fields: list[str] = Field(default_factory=list)
    """Fields that must be present in the handoff payload."""

    preserved_entities: list[str] = Field(default_factory=list)
    """Entity surfaces whose fidelity is scored by the ``Scorer``.

    When non-empty, ``min_fidelity`` must be explicitly set.
    """

    min_fidelity: float | None = Field(default=None, ge=0.0, le=1.0)
    """Floor for scored fidelity; required when ``preserved_entities`` is non-empty."""

    forbidden_drops: list[str] = Field(default_factory=list)
    """Fields that must not be removed at the handoff boundary."""

    @field_validator("required_fields", "preserved_entities", "forbidden_drops")
    @classmethod
    def _reject_duplicates(cls, v: list[str], info: ValidationInfo) -> list[str]:
        counts = Counter(v)
        dups = sorted(k for k, n in counts.items() if n > 1)
        if dups:
            raise ValueError(f"{info.field_name}: duplicate entries not allowed ({dups!r})")
        return v

    @model_validator(mode="after")
    def _reject_required_forbidden_overlap(self) -> ContractFields:
        overlap = sorted(set(self.required_fields) & set(self.forbidden_drops))
        if overlap:
            raise ValueError(
                f"required_fields and forbidden_drops must not intersect; overlap={overlap!r}"
            )
        return self

    @model_validator(mode="after")
    def _min_fidelity_required_when_preserved_entities(self) -> ContractFields:
        if self.preserved_entities and self.min_fidelity is None:
            raise ValueError(
                "min_fidelity must be provided when preserved_entities is non-empty; "
                "fidelity scoring requires an explicit threshold"
            )
        return self


class HandoffContract(BaseModel):
    """A single handoff-integrity contract.

    Consumed by the evaluator (PRC-013). Produced by every frontend:
    YAML loader, decorator frontend, and any future parser that conforms
    to ADR 0001.

    Construction raises ``precept.errors.ContractValidationError`` on
    any schema violation (wrapping Pydantic's native ``ValidationError``).
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    """Stable identifier; must match ``NAME_PATTERN``."""

    version: str = "0.1"
    """Opaque version string. Breaking-change semantics are deferred (Phase 2)."""

    mode: Literal["block", "warn"] = "warn"
    """``block`` raises ``HandoffBlockedError`` on violation; ``warn`` emits only."""

    fields: ContractFields
    """The rule set. May be all-empty for scaffold/observe-only contracts."""

    description: str | None = None
    """Free-form human description for docs and error context."""

    metadata: dict[str, str] = Field(default_factory=dict)
    """String-keyed, string-valued annotations. Typed values are out of scope at v0."""

    def __init__(self, **data: Any) -> None:
        try:
            super().__init__(**data)
        except ValidationError as exc:
            raise ContractValidationError.from_pydantic(exc) from exc

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        if not NAME_PATTERN.match(v):
            raise ValueError(f"name must match {NAME_PATTERN.pattern!r}, got {v!r}")
        return v
