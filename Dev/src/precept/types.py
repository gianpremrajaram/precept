# SPDX-License-Identifier: Apache-2.0
"""``ViolationEvent`` -- the canonical handoff-evaluation event shape.

The :class:`precept.evaluator.engine.Evaluator` (PRC-013) emits one
:class:`ViolationEvent` per handoff evaluation. Exporters (PRC-013
``Exporter`` ABC, PRC-020 OTel, PRC-021 JSON) consume the event
verbatim. The LangGraph integration (PRC-014) chooses to raise
:class:`precept.errors.HandoffBlockedError` based on ``event.mode`` and
``event.passed``; the evaluator itself never raises on a violation.

The :meth:`ViolationEvent.to_compact_dict` method projects the event
into a flat ``str/int/float/bool``-only dict whose JSON serialisation
fits inside 4 KiB. 4 KiB is the realistic OTel-attribute lower bound
across backends (Datadog, Jaeger; OpenObserve at 8 KiB, Honeycomb at
64 KiB but discouraging large attributes). Events exceeding the limit
are silently dropped by some backends; truncation here is preferable to
silent loss.

Truncation order (under size pressure): target summary keys first
(longest value first), then source summary keys. A
``precept.payload_truncated: True`` attribute is added the moment any
drop occurs, so backends can flag and operators can inspect.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from precept.evaluator.rules import RuleResult
from precept.scoring.base import ScoreResult

__all__ = [
    "ViolationEvent",
]


_COMPACT_LIMIT_BYTES = 4096
"""4 KiB ceiling on ``to_compact_dict()`` JSON serialisation. See
module docstring for backend rationale."""


class ViolationEvent(BaseModel):
    """One handoff evaluation, in event form.

    Carries enough detail (rule-by-rule, field-by-field, full
    :class:`ScoreResult`) for downstream consumers to reconstruct the
    evaluation without re-running it. Field-level interpretation is
    documented per attribute.

    See module docstring for the 4 KiB compact-dict ceiling and the
    target-then-source truncation strategy.
    """

    model_config = ConfigDict(extra="forbid")

    contract_name: str
    """``HandoffContract.name`` of the contract under which this event
    was produced."""

    contract_version: str
    """``HandoffContract.version`` of the contract; surfaces alongside
    ``contract_name`` so consumers can disambiguate revisions."""

    mode: Literal["block", "warn"]
    """Echo of ``HandoffContract.mode``. The integration layer (PRC-014)
    uses ``(mode, passed)`` to decide whether to raise
    :class:`HandoffBlockedError`; the evaluator itself never raises."""

    passed: bool
    """Authoritative violation flag. ``True`` iff every rule passed AND
    every per-field score passed. ``mode`` is metadata and does not
    influence this value."""

    score_result: ScoreResult
    """Full scorer output including per-field detail."""

    rule_results: list[RuleResult]
    """One entry per rule (required-fields, preserved-entities,
    forbidden-drops). Order matches the evaluator's invocation order."""

    triggered_at_iso: str
    """ISO 8601 UTC timestamp at evaluation time. Producers should use
    ``datetime.now(timezone.utc).isoformat()``. Naive datetimes and
    non-UTC offsets are rejected; a trailing ``Z`` is normalised to
    ``+00:00`` so the Python 3.10 ``fromisoformat`` floor parses it."""

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    """UUID4 identifier; unique per event. Used by exporters for
    best-effort idempotent dedup on retry."""

    source_summary: dict[str, str]
    """Per-field stringified source payload, one entry per contracted
    field. Values are truncated at 100 chars by the evaluator before
    construction."""

    target_summary: dict[str, str]
    """Per-field stringified target payload, one entry per contracted
    field. Values are truncated at 100 chars by the evaluator before
    construction."""

    schema_version: Literal["0.1"] = "0.1"
    """Bumped on any breaking change to the event shape. Exporters and
    downstream consumers may use this to pick a deserialiser."""

    @field_validator("triggered_at_iso")
    @classmethod
    def _validate_triggered_at_utc(cls, v: str) -> str:
        # Mirrors ``ScoreResult._validate_timestamp_iso_utc`` (PRC-010).
        err = (
            "triggered_at_iso must be a UTC-offset ISO 8601 string "
            "(e.g. 2026-05-02T21:00:00+00:00); naive datetimes and "
            "non-UTC offsets are not accepted"
        )
        candidate = v[:-1] + "+00:00" if v.endswith("Z") else v
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError as exc:
            raise ValueError(err) from exc
        if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
            raise ValueError(err)
        return v

    def to_compact_dict(self) -> dict[str, str | int | float | bool]:
        """Project the event to an OTel-attribute-friendly flat dict.

        All values are leaf scalars (``str``, ``int``, ``float``,
        ``bool``); no nested dicts at the top level. JSON serialisation
        of the result is guaranteed to be <= 4 KiB (see module
        docstring for rationale). When truncation occurs,
        ``precept.payload_truncated: True`` is set.
        """
        d: dict[str, str | int | float | bool] = {
            "precept.contract_name": self.contract_name,
            "precept.contract_version": self.contract_version,
            "precept.mode": self.mode,
            "precept.passed": self.passed,
            "precept.event_id": self.event_id,
            "precept.schema_version": self.schema_version,
            "precept.triggered_at_iso": self.triggered_at_iso,
            "precept.score.overall": self.score_result.overall_score,
            "precept.score.scorer_name": self.score_result.scorer_name,
            "precept.score.scorer_version": self.score_result.scorer_version,
            "precept.score.timestamp_iso": self.score_result.timestamp_iso,
        }
        for fs in self.score_result.field_scores:
            d[f"precept.score.field.{fs.field_name}.score"] = fs.score
            d[f"precept.score.field.{fs.field_name}.method"] = fs.method
            d[f"precept.score.field.{fs.field_name}.passed"] = fs.passed
        for r in self.rule_results:
            d[f"precept.rule.{r.rule_name}.passed"] = r.passed
            if r.violation_message is not None:
                d[f"precept.rule.{r.rule_name}.violation_message"] = r.violation_message
        for name, value in self.source_summary.items():
            d[f"precept.source.{name}"] = value
        for name, value in self.target_summary.items():
            d[f"precept.target.{name}"] = value

        while _byte_size(d) > _COMPACT_LIMIT_BYTES:
            # Set the flag on entry rather than after a successful drop:
            # this way an irreducible-overflow event (no source/target
            # keys but base shape already over budget) still surfaces a
            # truthful signal to backends. Dict assignment of an existing
            # key does not grow the dict, so the ~36 flag bytes are paid
            # exactly once across the whole truncation loop.
            d["precept.payload_truncated"] = True
            if _drop_largest_with_prefix(d, "precept.target."):
                continue
            if _drop_largest_with_prefix(d, "precept.source."):
                continue
            # No droppable summary keys remain. The event is still over
            # the limit; the flag set above tells operators the event is
            # over-budget even though we could not shrink it.
            break
        return d


def _byte_size(d: dict[str, str | int | float | bool]) -> int:
    """Byte length of ``d``'s JSON serialisation under the chosen
    separators. Centralised so the size measurement is consistent
    between truncation decisions and the downstream test assertions."""
    return len(json.dumps(d, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _drop_largest_with_prefix(
    d: dict[str, str | int | float | bool],
    prefix: str,
) -> bool:
    """Drop the entry under ``prefix`` whose stringified value is longest.

    Returns ``True`` if a key was dropped, ``False`` if no key under
    ``prefix`` exists. Used by ``to_compact_dict`` for the
    target-then-source truncation order.
    """
    candidates = [k for k in d if k.startswith(prefix)]
    if not candidates:
        return False
    longest = max(candidates, key=lambda k: len(str(d[k])))
    del d[longest]
    return True
