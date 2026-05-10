# SPDX-License-Identifier: MIT
"""Per-field rule evaluators (PRC-012).

Three pure functions check structural properties of a handoff payload
pair. They are deliberately stateless, side-effect-free, and never
raise; rule failures are returned as ``RuleResult`` data so the caller
(``Evaluator``, PRC-013) can aggregate them into a ``ViolationEvent``
without exception-flow plumbing.

Per ``CLAUDE.md`` -> "When to use classes vs functions": rules hold no
state and compose orthogonally, so they live as module-level functions
rather than methods on a hypothetical ``Rule`` ABC. Adding such a
class would be premature abstraction at v0.

All three rules read ``HandoffPayload.fields`` only. They do NOT
consult ``HandoffPayload.raw`` (optional, ``str | None``); ``raw`` is
free-form and may be unset, so reading it would make rule behaviour
depend on whether the producer happened to populate it. The
contracted-fields-only discipline (see ``CLAUDE.md`` -> "Contracted-
fields-only extraction") keeps rule behaviour stable across producers.

Every ``RuleResult.details`` payload has a documented stable shape;
PRC-013's ``ViolationEvent`` renderer relies on these shapes, so
widening or renaming a key is a breaking change.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from precept.scoring.base import HandoffPayload

__all__ = [
    "RuleResult",
    "forbidden_drops_rule",
    "preserved_entities_rule",
    "required_fields_rule",
]


class RuleResult(BaseModel):
    """Result of a single rule evaluation.

    Rules are pure functions; failures are data, not exceptions. A
    ``passed=False`` result carries a non-empty ``violation_message``
    suitable for human display. ``details`` is rule-specific structured
    data; see each rule's docstring for the exact shape.
    """

    model_config = ConfigDict(extra="forbid")

    rule_name: str
    """Stable identifier of the rule that produced this result. Matches
    the ``_RULE_*`` constants in this module."""

    passed: bool
    """``True`` iff the rule's invariant holds for the given payload pair."""

    details: dict[str, Any] = Field(default_factory=dict)
    """Rule-specific structured detail. Each rule documents its key
    set explicitly; PRC-013's ``ViolationEvent`` renderer relies on
    that contract."""

    violation_message: str | None = None
    """Human-readable description of the violation. ``None`` when
    ``passed`` is ``True``."""


_RULE_REQUIRED_FIELDS = "required_fields"
_RULE_PRESERVED_ENTITIES = "preserved_entities"
_RULE_FORBIDDEN_DROPS = "forbidden_drops"


def required_fields_rule(
    source: HandoffPayload,
    target: HandoffPayload,
    required: list[str],
) -> RuleResult:
    """Verify every name in ``required`` is a key in ``target.fields``.

    ``source`` is unused by this rule; the parameter is part of the
    common rule signature so all rules compose uniformly in PRC-013's
    ``Evaluator``.

    Empty ``required`` -> always pass.

    ``RuleResult.details`` shape::

        {"required": list[str], "missing": list[str]}

    where ``missing`` lists the fields that were declared but absent
    in ``target.fields`` (preserving the order of ``required``).
    ``missing`` is empty on pass.
    """
    missing = [name for name in required if name not in target.fields]
    passed = not missing
    return RuleResult(
        rule_name=_RULE_REQUIRED_FIELDS,
        passed=passed,
        details={"required": list(required), "missing": missing},
        violation_message=_required_message(missing) if missing else None,
    )


def preserved_entities_rule(
    source: HandoffPayload,
    target: HandoffPayload,
    entities: list[str],
) -> RuleResult:
    """Verify every entity present in source's content is also in target's.

    Reads ``HandoffPayload.fields`` only; values are stringified via
    ``str()`` and joined with newlines to form a search haystack.
    ``raw`` is intentionally not consulted (see module docstring).

    Matching is case-insensitive substring (v0). NER-based entity
    matching is deferred to PRC-030; substring matching produces both
    false positives ("Smith" matches many strings) and false negatives
    (morphological variants). The limitation is documented wherever
    this rule is exposed to users.

    Vacuous-pass semantics: an entity NOT present in the source's
    content also passes (nothing to preserve). This mirrors
    ``forbidden_drops_rule`` (target-only fields are not violations).
    Only entities that *were* in the source and are *missing* in the
    target produce failures.

    Empty ``entities`` -> always pass.

    ``RuleResult.details`` shape::

        {"entities": list[str], "missing": list[str]}

    where ``missing`` is the list of entities found in source but
    absent in target (preserving the order of ``entities``).
    ``missing`` is empty on pass.
    """
    src_blob = _stringify_fields(source).casefold()
    tgt_blob = _stringify_fields(target).casefold()
    missing = [
        entity
        for entity in entities
        if entity.casefold() in src_blob and entity.casefold() not in tgt_blob
    ]
    passed = not missing
    return RuleResult(
        rule_name=_RULE_PRESERVED_ENTITIES,
        passed=passed,
        details={"entities": list(entities), "missing": missing},
        violation_message=_preserved_message(missing) if missing else None,
    )


def forbidden_drops_rule(
    source: HandoffPayload,
    target: HandoffPayload,
    forbidden: list[str],
) -> RuleResult:
    """Verify no field in ``forbidden`` is present in source but absent in target.

    For each name in ``forbidden``: present in source AND absent in
    target -> violation. Present in target only -> pass (nothing was
    dropped). Present in both -> pass.

    Empty ``forbidden`` -> always pass.

    ``RuleResult.details`` shape::

        {"forbidden": list[str], "dropped": list[str]}

    where ``dropped`` is the list of fields that were present in
    source but absent in target (preserving the order of
    ``forbidden``). ``dropped`` is empty on pass.
    """
    dropped = [name for name in forbidden if name in source.fields and name not in target.fields]
    passed = not dropped
    return RuleResult(
        rule_name=_RULE_FORBIDDEN_DROPS,
        passed=passed,
        details={"forbidden": list(forbidden), "dropped": dropped},
        violation_message=_dropped_message(dropped) if dropped else None,
    )


def _stringify_fields(payload: HandoffPayload) -> str:
    """Join stringified field values with newlines.

    ``str()`` on the value, not ``repr()``; newline-joined so that
    overlapping substrings across fields don't accidentally form
    spurious matches at field boundaries (e.g. field ``a="...Smith"``
    followed by field ``b="Doe..."`` should not match the literal
    entity ``"SmithDoe"``).
    """
    return "\n".join(str(value) for value in payload.fields.values())


def _required_message(missing: list[str]) -> str:
    if len(missing) == 1:
        return f"Required field {missing[0]!r} missing in target payload"
    names = ", ".join(repr(n) for n in missing)
    return f"Required fields {names} missing in target payload"


def _preserved_message(missing: list[str]) -> str:
    if len(missing) == 1:
        return f"Preserved entity {missing[0]!r} present in source but missing in target"
    names = ", ".join(repr(e) for e in missing)
    return f"Preserved entities {names} present in source but missing in target"


def _dropped_message(dropped: list[str]) -> str:
    if len(dropped) == 1:
        return f"Forbidden drop: field {dropped[0]!r} present in source but absent in target"
    names = ", ".join(repr(n) for n in dropped)
    return f"Forbidden drops: fields {names} present in source but absent in target"
